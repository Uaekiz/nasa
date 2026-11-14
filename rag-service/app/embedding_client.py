"""Generate validated embeddings with the local Ollama API."""

from dataclasses import dataclass
import math
import os
from time import perf_counter

import httpx

from .ollama_client import OLLAMA_BASE_URL


DEFAULT_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
MAX_BATCH_SIZE = 8
EMBEDDING_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


class EmbeddingError(RuntimeError):
    """An actionable embedding failure, independent of the answer API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EmbeddingResult:
    model: str
    embeddings: list[list[float]]
    elapsed_ms: float
    server_duration_ms: float | None
    load_duration_ms: float | None

    @property
    def dimensions(self) -> int:
        return len(self.embeddings[0])


def _invalid_response(message: str) -> EmbeddingError:
    return EmbeddingError("INVALID_EMBEDDING_RESPONSE", message)


def _duration_ms(data: dict, field: str) -> float | None:
    value = data.get(field)
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise _invalid_response(f"Ollama returned an invalid {field}; expected nonnegative nanoseconds.")
    try:
        milliseconds = value / 1_000_000
    except OverflowError as error:
        raise _invalid_response(f"Ollama returned an excessively large {field}.") from error
    if not math.isfinite(milliseconds):
        raise _invalid_response(f"Ollama returned a non-finite {field}.")
    return milliseconds


def _validate_vectors(data: object, expected_count: int) -> tuple[str, list[list[float]]]:
    if not isinstance(data, dict) or "error" in data:
        raise _invalid_response("Ollama did not return a successful embedding JSON object.")
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise _invalid_response("Ollama's embedding response is missing a valid model name.")
    vectors = data.get("embeddings")
    if not isinstance(vectors, list) or len(vectors) != expected_count:
        raise _invalid_response(f"Ollama must return exactly {expected_count} embedding vectors.")
    dimensions = None
    validated = []
    for index, vector in enumerate(vectors, start=1):
        if not isinstance(vector, list) or not vector:
            raise _invalid_response(f"Embedding vector {index} must be a nonempty numeric array.")
        if dimensions is None:
            dimensions = len(vector)
        elif len(vector) != dimensions:
            raise _invalid_response("Ollama returned embedding vectors with inconsistent dimensions.")
        values = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _invalid_response(f"Embedding vector {index} contains a nonnumeric value.")
            try:
                number = float(value)
            except OverflowError as error:
                raise _invalid_response(f"Embedding vector {index} contains an excessively large value.") from error
            if not math.isfinite(number):
                raise _invalid_response(f"Embedding vector {index} contains a non-finite value.")
            values.append(number)
        validated.append(values)
    return model, validated


async def embed_texts(
    texts: str | list[str],
    *,
    client: httpx.AsyncClient | None = None,
) -> EmbeddingResult:
    """Embed one text or up to eight texts in input order, with truncation disabled.

    A supplied HTTP client remains owned by the caller. No retries, model
    downloads, text transformations, dimension overrides, or persistence occur.
    """
    if isinstance(texts, str):
        inputs = [texts]
    elif isinstance(texts, list):
        inputs = list(texts)
    else:
        raise EmbeddingError("INVALID_EMBEDDING_INPUT", "Input must be one text or a list of texts.")
    if not 1 <= len(inputs) <= MAX_BATCH_SIZE:
        raise EmbeddingError(
            "INVALID_EMBEDDING_INPUT", f"Provide between 1 and {MAX_BATCH_SIZE} texts per request."
        )
    if any(not isinstance(text, str) or not text.strip() for text in inputs):
        raise EmbeddingError("INVALID_EMBEDDING_INPUT", "Every embedding input must be nonempty text.")
    model = os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    if not model:
        raise EmbeddingError("EMBEDDING_CONFIGURATION_ERROR", "OLLAMA_EMBEDDING_MODEL must not be empty.")
    payload = {
        "model": model,
        "input": inputs[0] if isinstance(texts, str) else inputs,
        "truncate": False,
    }
    started = perf_counter()
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT, trust_env=False) as local_client:
                response = await local_client.post(f"{OLLAMA_BASE_URL}/api/embed", json=payload)
        else:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/embed", json=payload, timeout=EMBEDDING_TIMEOUT
            )
    except httpx.TimeoutException as error:
        raise EmbeddingError(
            "EMBEDDING_TIMEOUT",
            f"Ollama embedding request timed out at {OLLAMA_BASE_URL}. "
            "Check model loading and server availability before retrying.",
        ) from error
    except httpx.RequestError as error:
        raise EmbeddingError(
            "OLLAMA_UNAVAILABLE",
            f"Cannot reach Ollama at {OLLAMA_BASE_URL}. Check the server and OLLAMA_BASE_URL.",
        ) from error

    if response.is_error:
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("error"), str):
                detail = body["error"]
        except ValueError:
            pass
        if response.status_code == 404 and "model" in detail.lower():
            raise EmbeddingError(
                "MODEL_UNAVAILABLE",
                f"Embedding model '{model}' is unavailable in Ollama. "
                "Install it or set OLLAMA_EMBEDDING_MODEL to an installed embedding model.",
            )
        message = f"Ollama rejected the embedding request (HTTP {response.status_code})."
        if detail:
            message += f" {detail}"
        raise EmbeddingError("EMBEDDING_REQUEST_FAILED", message + " Input was not truncated.")
    try:
        data = response.json()
    except ValueError as error:
        raise _invalid_response("Ollama returned invalid JSON for the embedding request.") from error
    response_model, vectors = _validate_vectors(data, len(inputs))
    server_duration = _duration_ms(data, "total_duration")
    load_duration = _duration_ms(data, "load_duration")
    return EmbeddingResult(
        model=response_model,
        embeddings=vectors,
        elapsed_ms=(perf_counter() - started) * 1000,
        server_duration_ms=server_duration,
        load_duration_ms=load_duration,
    )
