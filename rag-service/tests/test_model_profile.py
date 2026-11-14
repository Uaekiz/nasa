import os
import unittest
from unittest.mock import patch

import httpx

from app.model_profile import QUERY_INSTRUCTION, format_query, get_model_profile, verify_model_identity
from app.rag_config import RagError


class ModelProfileTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict(os.environ, {"OLLAMA_EMBEDDING_MODEL": "qwen3-embedding:0.6b"})
        environment.start()
        self.addCleanup(environment.stop)

    def metadata(self, request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3-embedding:0.6b", "digest": "synthetic-test-digest"}]})
        return httpx.Response(200, json={
            "capabilities": ["embedding"],
            "model_info": {"general.architecture": "qwen3", "qwen3.embedding_length": 1024},
        })

    async def test_model_digest_and_dimensions_are_discovered_without_embedding(self):
        requests = []

        def metadata(request):
            requests.append(request.url.path)
            return self.metadata(request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(metadata)) as client:
            profile = await get_model_profile(client)
            await verify_model_identity(profile, client)
        self.assertEqual(profile.dimensions, 1024)
        self.assertEqual(profile.digest, "synthetic-test-digest")
        self.assertEqual(profile.query_instruction, QUERY_INSTRUCTION)
        self.assertNotIn("/api/embed", requests)

    async def test_query_format_matches_qwen_documented_instruction_pattern(self):
        question = "Find reported extinction tests."
        self.assertEqual(format_query(question), f"Instruct: {QUERY_INSTRUCTION}\nQuery:{question}")

    async def test_other_model_families_are_rejected_instead_of_using_wrong_query_format(self):
        with patch.dict(os.environ, {"OLLAMA_EMBEDDING_MODEL": "another-model:latest"}):
            async with httpx.AsyncClient(transport=httpx.MockTransport(self.metadata)) as client:
                with self.assertRaises(RagError) as caught:
                    await get_model_profile(client)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_MODEL")

    async def test_missing_model_identity_is_not_invented(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"models": []})
        )) as client:
            with self.assertRaises(RagError) as caught:
                await get_model_profile(client)
        self.assertEqual(caught.exception.code, "MODEL_UNAVAILABLE")
