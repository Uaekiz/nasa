from uuid import UUID
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .answer_service import answer_question
from .embedding_client import EmbeddingError
from .rag_config import RagError

logger = logging.getLogger(__name__)
RAG_REQUEST_TIMEOUT = 120.0

app = FastAPI(
    title="PyroSphere RAG Service",
    version="1.0.0",
)


class AnswerRequest(BaseModel):
    requestId: UUID
    question: str = Field(min_length=1, max_length=4000)
    investigationIds: list[str] = Field(default_factory=list)
    experimentIds: list[str] = Field(default_factory=list)
    analysisContext: dict | None = None


@app.get("/rag/v1/health")
def health():
    return {"status": "UP"}


@app.post("/rag/v1/answer")
async def answer(request: AnswerRequest):
    request_id = str(request.requestId)
    try:
        async with asyncio.timeout(RAG_REQUEST_TIMEOUT):
            return await answer_question(request)
    except TimeoutError:
        return error_response(request_id, 504, "RAG_TIMEOUT", "The RAG request exceeded its time limit.")
    except (RagError, EmbeddingError) as error:
        detail = error.code
        if "TIMEOUT" in detail:
            status, code = 504, "RAG_TIMEOUT"
        elif detail in {"INVALID_QUESTION", "INVALID_FILTER", "CONFLICTING_FILTER"}:
            status, code = 400, "VALIDATION_ERROR"
        elif detail in {"GENERATION_VALIDATION_FAILED", "INVALID_GENERATION_RESPONSE", "INVALID_EMBEDDING_RESPONSE"}:
            status, code = 503, "MODEL_UNAVAILABLE"
        elif "MODEL" in detail or detail.startswith(("OLLAMA_", "EMBEDDING_")):
            status, code = 503, "MODEL_UNAVAILABLE"
        else:
            status, code = 503, "RAG_UNAVAILABLE"
        return error_response(request_id, status, code, str(error), [{"code": detail}])
    except Exception as error:
        # Log the exception class only; driver exception text can include local credentials.
        logger.error("Unexpected answer failure: %s", type(error).__name__)
        return error_response(request_id, 500, "INTERNAL_ERROR", "An unexpected RAG service error occurred.")


def error_response(request_id, status, code, message, details=None):
    return JSONResponse(status_code=status, content={
        "requestId": request_id,
        "error": {"code": code, "message": message, "details": details or []},
    })


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    request_id = None
    if isinstance(error.body, dict):
        try:
            request_id = str(UUID(str(error.body.get("requestId"))))
        except ValueError:
            pass
    return error_response(request_id, 400, "VALIDATION_ERROR", "The answer request contains invalid or missing fields.")
