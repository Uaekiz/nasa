"""Configuration and errors for the independent persistence and retrieval CLIs."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
APP_DATABASE = "pyrosphere_rag"
APP_ROLE = "pyrosphere_rag_app"
load_dotenv(BASE_DIR / ".env", override=False)


class RagError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = field(repr=False)
    schema: str = "rag"

    def __post_init__(self):
        if not self.url.strip():
            raise RagError(
                "DATABASE_NOT_CONFIGURED",
                "Set RAG_DATABASE_URL in the environment or rag-service/.env. No credentials were guessed.",
            )
        if not re.fullmatch(r"(?:rag|pyrosphere_rag)(?:_[a-z0-9_]+)?", self.schema) or len(self.schema) > 63:
            raise RagError(
                "INVALID_RAG_SCHEMA", "RAG_DB_SCHEMA must be rag, rag_*, or a previously supported pyrosphere_rag schema."
            )

    @classmethod
    def from_environment(cls):
        return cls(os.getenv("RAG_DATABASE_URL", ""), os.getenv("RAG_DB_SCHEMA", "rag"))
