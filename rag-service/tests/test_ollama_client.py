"""Chat transport failures and structured response checks without live Ollama."""

import json
import unittest

import httpx

from app.ollama_client import OLLAMA_MODEL, generate_answer
from app.rag_config import RagError


class OllamaChatTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, handler, **kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await generate_answer("Read the supplied evidence.", client=client, **kwargs)

    async def test_schema_model_and_nonstreaming_payload(self):
        def handler(request):
            payload = json.loads(request.content)
            self.assertEqual(request.url.path, "/api/chat")
            self.assertFalse(payload["stream"])
            self.assertEqual(payload["format"], {"type": "object"})
            self.assertEqual(payload["model"], OLLAMA_MODEL)
            self.assertEqual(payload["options"]["temperature"], 0)
            return httpx.Response(200, json={"model": OLLAMA_MODEL, "done": True, "message": {"content": '{"records":[]}'}})
        self.assertEqual(await self.call(handler, response_schema={"type": "object"}), '{"records":[]}')

    async def test_unavailable_model_and_connection_failures(self):
        def offline(request):
            raise httpx.ConnectError("Local connection refused", request=request)
        for handler, code in ((lambda r: httpx.Response(404, json={"error": "model absent"}), "MODEL_UNAVAILABLE"), (offline, "OLLAMA_UNAVAILABLE")):
            with self.assertRaises(RagError) as raised:
                await self.call(handler)
            self.assertEqual(raised.exception.code, code)

    async def test_timeout(self):
        def timeout(request):
            raise httpx.ReadTimeout("Timed out", request=request)
        with self.assertRaises(RagError) as raised:
            await self.call(timeout)
        self.assertEqual(raised.exception.code, "GENERATION_TIMEOUT")

    async def test_invalid_and_truncated_response(self):
        for data in ({}, {"model": OLLAMA_MODEL, "done": True, "message": {"content": ""}},
                     {"model": "another-model", "done": True, "message": {"content": "wrong"}},
                     {"model": OLLAMA_MODEL, "done": True, "done_reason": "length", "message": {"content": "cut"}}):
            with self.assertRaises(RagError) as raised:
                await self.call(lambda request: httpx.Response(200, json=data))
            self.assertEqual(raised.exception.code, "INVALID_GENERATION_RESPONSE")


if __name__ == "__main__":
    unittest.main()
