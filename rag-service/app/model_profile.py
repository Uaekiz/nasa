"""Pin model identity and the documented Qwen3 query/document formatting."""

from dataclasses import asdict, dataclass
import os

import httpx

from .rag_config import RagError
from .embedding_client import DEFAULT_EMBEDDING_MODEL
from .ollama_client import OLLAMA_BASE_URL


QUERY_INSTRUCTION = "Given a question about NASA FLEX tests, retrieve original test records that directly address it."
DOCUMENT_FORMAT = "flex-raw-evidence-text-v1"
SCHEMA_VERSION = 1
MULTI_QUERY_INSTRUCTION = "Given a question about the selected NASA PSI investigation and source, retrieve original source rows that directly address it."


def expected_profile(model, digest, dimensions, *, schema_version=None):
    if schema_version not in (None, 1, 2):
        raise RagError("INCOMPATIBLE_INDEX", "Unrecognized index schema version")
    if schema_version == 2 or (schema_version is None and os.getenv("RAG_CORPUS_MODE", "flex") == "multi"):
        return ModelProfile(model, digest, dimensions, "nasa-source-evidence-v2", MULTI_QUERY_INSTRUCTION, 2)
    return ModelProfile(model, digest, dimensions)


def format_query(question: str, profile=None) -> str:
    return f"Instruct: {profile.query_instruction if profile else QUERY_INSTRUCTION}\nQuery:{question}"


@dataclass(frozen=True)
class ModelProfile:
    model: str
    digest: str
    dimensions: int
    document_format: str = DOCUMENT_FORMAT
    query_instruction: str = QUERY_INSTRUCTION
    schema_version: int = SCHEMA_VERSION

    @property
    def configuration(self) -> dict:
        return asdict(self)


async def _json_request(client: httpx.AsyncClient, method: str, endpoint: str, **kwargs) -> dict:
    try:
        response = await client.request(method, f"{OLLAMA_BASE_URL}{endpoint}", timeout=30.0, **kwargs)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as error:
        raise RagError("MODEL_TIMEOUT", "Ollama model identity inspection timed out.") from error
    except httpx.HTTPError as error:
        raise RagError("MODEL_UNAVAILABLE", "Cannot inspect the installed Ollama embedding model.") from error
    except ValueError as error:
        raise RagError("INVALID_MODEL_RESPONSE", "Ollama returned invalid model metadata JSON.") from error
    if not isinstance(data, dict):
        raise RagError("INVALID_MODEL_RESPONSE", "Ollama model metadata must be a JSON object.")
    return data


async def model_tag(client: httpx.AsyncClient) -> dict:
    configured = os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
    # Other model families require an explicitly implemented query formatting policy.
    if not configured.startswith("qwen3-embedding:"):
        raise RagError("UNSUPPORTED_MODEL", "Retrieval currently requires an explicit qwen3-embedding model tag.")
    data = await _json_request(client, "GET", "/api/tags")
    models = data.get("models")
    if not isinstance(models, list):
        raise RagError("INVALID_MODEL_RESPONSE", "Ollama did not return a model list.")
    matches = [model for model in models if isinstance(model, dict) and model.get("name") == configured]
    if len(matches) != 1 or not isinstance(matches[0].get("digest"), str) or not matches[0]["digest"]:
        raise RagError("MODEL_UNAVAILABLE", f"No installed model identity was found for {configured}.")
    return matches[0]


async def get_model_profile(client: httpx.AsyncClient) -> ModelProfile:
    tag = await model_tag(client)
    details = await _json_request(client, "POST", "/api/show", json={"model": tag["name"]})
    info = details.get("model_info", {})
    if not isinstance(info, dict) or info.get("general.architecture") != "qwen3":
        raise RagError("UNSUPPORTED_MODEL", "The configured model is not a supported Qwen3 embedding model.")
    dimensions = info.get("qwen3.embedding_length")
    if type(dimensions) is not int or not 1 <= dimensions <= 16000:
        raise RagError("INVALID_MODEL_RESPONSE", "Ollama did not report valid embedding dimensions.")
    if not isinstance(details.get("capabilities"), list) or "embedding" not in details["capabilities"]:
        raise RagError("UNSUPPORTED_MODEL", "The configured model does not advertise embedding support.")
    return expected_profile(tag["name"], tag["digest"], dimensions)


async def verify_model_identity(profile: ModelProfile, client: httpx.AsyncClient) -> None:
    tag = await model_tag(client)
    if tag["name"] != profile.model or tag["digest"] != profile.digest:
        raise RagError("INCOMPATIBLE_INDEX", "The embedding model tag or digest changed during this operation.")
