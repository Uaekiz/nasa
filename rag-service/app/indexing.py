"""Batch indexing CLI with durable commits and embedding reuse."""

import argparse
import asyncio
from functools import partial
import json
import sys
from time import perf_counter

import httpx

from .rag_config import DatabaseSettings, RagError
from .rag_corpus import Corpus, content_hash, load_corpus, record_key, text_hash
from .model_profile import ModelProfile, get_model_profile, verify_model_identity
from .embedding_client import EMBEDDING_TIMEOUT, MAX_BATCH_SIZE, EmbeddingError, embed_texts
from .vector_store import open_store, vector_literal


async def index_corpus(
    store, corpus: Corpus, profile: ModelProfile, *, batch_size: int = 8,
    embed=embed_texts, check_identity=None, progress=None,
) -> dict:
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise RagError("INVALID_BATCH_SIZE", f"Batch size must be between 1 and {MAX_BATCH_SIZE}.")
    started = perf_counter()
    store.bootstrap(profile)
    cache = store.cache()
    if set(cache) - set(corpus.by_key):
        raise RagError("INCOMPLETE_SOURCE_SCOPE", "The incoming snapshot omits persisted source rows. No existing rows were deleted; use a complete reviewed catalog or a new schema.")
    dirty = []
    needs_embedding = set()
    for record in corpus.records:
        existing = cache.get(record_key(record))
        if existing is None or existing["text_hash"] != text_hash(record):
            needs_embedding.add(record_key(record))
        if (
            existing is None or existing["content_hash"] != content_hash(record)
            or existing["text_hash"] != text_hash(record) or existing["record"] != record
        ):
            dirty.append(record)
    state = store.state()
    already_ready = (
        not dirty and set(cache) == set(corpus.by_key)
        and state["status"] == "READY" and state["corpus_hash"] == corpus.fingerprint
        and state["expected_count"] == len(corpus.records)
    )
    embedded = 0
    embedding_ms = 0.0
    load_ms = 0.0
    completed = len(corpus.records) - len(dirty)
    if not already_ready:
        store.begin_snapshot(corpus)
        for start in range(0, len(dirty), batch_size):
            batch = dirty[start:start + batch_size]
            pending = [record for record in batch if record_key(record) in needs_embedding]
            vectors = {}
            if pending:
                if check_identity is not None:
                    await check_identity()
                result = await embed([record["text"] for record in pending])
                if result.model != profile.model or result.dimensions != profile.dimensions:
                    raise RagError("INCOMPATIBLE_INDEX", "Embedding model or dimensions differ from the pinned index.")
                if len(result.embeddings) != len(pending):
                    raise RagError("INVALID_VECTOR", "The embedding batch returned an incorrect vector count.")
                for record, vector in zip(pending, result.embeddings, strict=True):
                    vector_literal(vector, profile.dimensions)
                    vectors[record_key(record)] = vector
                if check_identity is not None:
                    await check_identity()
                embedding_ms += result.elapsed_ms
                load_ms += result.load_duration_ms or 0.0
            store.write_batch(batch, vectors)
            embedded += len(pending)
            completed += len(batch)
            if progress is not None:
                progress(completed, len(corpus.records), embedded)
        store.finish_snapshot(corpus)
    return {
        "indexedRecordCount": len(corpus.records), "embeddedRecords": embedded,
        "reusedEmbeddings": len(corpus.records) - embedded,
        "model": profile.model, "modelDigest": profile.digest, "dimensions": profile.dimensions,
        "corpusHash": corpus.fingerprint, "status": "READY",
        "indexingMs": round((perf_counter() - started) * 1000, 3),
        "embeddingMs": round(embedding_ms, 3), "modelLoadMs": round(load_ms, 3),
    }


async def run_index(batch_size: int) -> dict:
    started = perf_counter()
    settings = DatabaseSettings.from_environment()
    corpus = load_corpus()
    with open_store(settings) as store, store.lock():
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT, trust_env=False) as client:
            profile = await get_model_profile(client)
            result = await index_corpus(
                store, corpus, profile, batch_size=batch_size,
                embed=partial(embed_texts, client=client),
                check_identity=partial(verify_model_identity, profile, client),
                progress=lambda done, total, embedded: print(
                    f"Committed records: {done}/{total}; newly embedded: {embedded}.", file=sys.stderr, flush=True
                ),
            )
    result["totalIndexingMs"] = round((perf_counter() - started) * 1000, 3)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist the validated FLEX corpus in the RAG pgvector schema.")
    parser.add_argument("--batch-size", type=int, choices=range(1, MAX_BATCH_SIZE + 1), default=8)
    args = parser.parse_args()
    try:
        result = asyncio.run(run_index(args.batch_size))
    except (RagError, EmbeddingError) as error:
        print(f"Error [{error.code}]: {error}", file=sys.stderr)
        print("Previously committed batches are preserved. Correct the problem and rerun to resume.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Indexing interrupted. Previously committed batches are preserved; rerun to resume.", file=sys.stderr)
        return 130
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
