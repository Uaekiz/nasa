import json
import math
import os
import unittest
from unittest.mock import patch

import httpx

from app.embedding_client import EmbeddingError, MAX_BATCH_SIZE, embed_texts


class EmbeddingClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict(os.environ, {"OLLAMA_EMBEDDING_MODEL": "qwen3-embedding:0.6b"})
        environment.start()
        self.addCleanup(environment.stop)
        self.requests = []

    async def embed_response(self, body, texts="Synthetic embedding input.", *, status=200):
        def respond(request):
            self.requests.append(request)
            # Raw response bytes permit deliberately invalid NaN/Infinity fixtures.
            return httpx.Response(
                status,
                content=json.dumps(body, allow_nan=True).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await embed_texts(texts, client=client)

    async def test_single_input_uses_embed_endpoint_and_disables_truncation(self):
        original = "  Synthetic original field; mm: >0.5\n  "
        result = await self.embed_response({
            "model": "qwen3-embedding:0.6b", "embeddings": [[0.5, -1, 0]],
            "total_duration": 2_500_000, "load_duration": 500_000,
        }, original)
        request = self.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url.path, "/api/embed")
        self.assertEqual(json.loads(request.content), {
            "model": "qwen3-embedding:0.6b", "input": original, "truncate": False,
        })
        self.assertEqual(result.embeddings, [[0.5, -1.0, 0.0]])
        self.assertEqual(result.dimensions, 3)
        self.assertEqual(result.server_duration_ms, 2.5)
        self.assertEqual(result.load_duration_ms, 0.5)
        self.assertGreaterEqual(result.elapsed_ms, 0)

    async def test_batch_preserves_order_and_caller_owned_client(self):
        texts = ["Synthetic record A.", "Synthetic record B.", "An English query?"]

        def respond(request):
            self.requests.append(request)
            return httpx.Response(200, json={
                "model": "test-embedding", "embeddings": [[1, 0], [0, 1], [-1, 0]],
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await embed_texts(texts, client=client)
            self.assertFalse(client.is_closed)
        self.assertEqual(json.loads(self.requests[0].content)["input"], texts)
        self.assertEqual(result.embeddings, [[1, 0], [0, 1], [-1, 0]])
        self.assertIsNone(result.server_duration_ms)
        self.assertIsNone(result.load_duration_ms)

    async def test_embedding_model_is_configured_independently_from_chat(self):
        with patch.dict(os.environ, {
            "OLLAMA_MODEL": "chat-only-model", "OLLAMA_EMBEDDING_MODEL": "configured-embedding",
        }):
            await self.embed_response({"model": "configured-embedding", "embeddings": [[1]]})
        self.assertEqual(json.loads(self.requests[0].content)["model"], "configured-embedding")

    async def test_invalid_inputs_are_rejected_before_network_access(self):
        for texts in ("", " \n", [], ["valid", ""], [1], None, ("text",), ["text"] * (MAX_BATCH_SIZE + 1)):
            with self.subTest(texts=texts):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response({}, texts)
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_INPUT")
        self.assertEqual(self.requests, [])

    async def test_empty_configured_model_is_rejected_before_network_access(self):
        with patch.dict(os.environ, {"OLLAMA_EMBEDDING_MODEL": " "}):
            with self.assertRaises(EmbeddingError) as caught:
                await self.embed_response({})
        self.assertEqual(caught.exception.code, "EMBEDDING_CONFIGURATION_ERROR")
        self.assertEqual(self.requests, [])

    async def test_wrong_vector_counts_are_rejected(self):
        for vectors in (None, [], [[1]], [[1], [2], [3]], "invalid"):
            with self.subTest(vectors=vectors):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response({"model": "test", "embeddings": vectors}, ["A", "B"])
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_RESPONSE")

    async def test_empty_and_inconsistent_dimensions_are_rejected(self):
        for vectors in (([],), [[1], []], [[1, 2], [3]], [[1], "invalid"]):
            vectors = list(vectors)
            with self.subTest(vectors=vectors):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response({"model": "test", "embeddings": vectors}, ["text"] * len(vectors))
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_RESPONSE")

    async def test_nonnumeric_boolean_and_nonfinite_values_are_rejected(self):
        for value in (None, True, False, "0.5", {}, [], math.nan, math.inf, -math.inf, 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response({"model": "test", "embeddings": [[value]]})
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_RESPONSE")

    async def test_invalid_response_object_or_model_is_rejected(self):
        for body in ([], None, {}, {"error": "failure"}, {"model": "", "embeddings": [[1]]}):
            with self.subTest(body=body):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response(body)
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_RESPONSE")

    async def test_invalid_timing_metadata_is_rejected(self):
        for value in (-1, True, "10", 1.5, 10 ** 1000):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(EmbeddingError) as caught:
                    await self.embed_response({
                        "model": "test", "embeddings": [[1]], "total_duration": value,
                    })
                self.assertEqual(caught.exception.code, "INVALID_EMBEDDING_RESPONSE")

    async def test_missing_model_has_an_actionable_error(self):
        with self.assertRaises(EmbeddingError) as caught:
            await self.embed_response({"error": "model 'missing' not found"}, status=404)
        self.assertEqual(caught.exception.code, "MODEL_UNAVAILABLE")
        self.assertIn("OLLAMA_EMBEDDING_MODEL", str(caught.exception))

    async def test_context_overflow_is_reported_without_retrying_or_truncating(self):
        with self.assertRaises(EmbeddingError) as caught:
            await self.embed_response({"error": "input length exceeds context length"}, status=400)
        self.assertEqual(caught.exception.code, "EMBEDDING_REQUEST_FAILED")
        self.assertIn("input length exceeds context length", str(caught.exception))
        self.assertIn("Input was not truncated", str(caught.exception))
        self.assertEqual(len(self.requests), 1)

    async def test_invalid_json_and_non_json_server_errors_are_clear(self):
        for status in (200, 500):
            with self.subTest(status=status):
                async with httpx.AsyncClient(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, content=b"Not JSON.")
                )) as client:
                    with self.assertRaises(EmbeddingError) as caught:
                        await embed_texts("text", client=client)
                expected = "INVALID_EMBEDDING_RESPONSE" if status == 200 else "EMBEDDING_REQUEST_FAILED"
                self.assertEqual(caught.exception.code, expected)

    async def test_timeouts_and_unavailable_server_are_distinct(self):
        for exception_type, code in (
            (httpx.ReadTimeout, "EMBEDDING_TIMEOUT"),
            (httpx.ConnectTimeout, "EMBEDDING_TIMEOUT"),
            (httpx.ConnectError, "OLLAMA_UNAVAILABLE"),
        ):
            with self.subTest(exception_type=exception_type):
                calls = []

                def fail(request):
                    calls.append(request)
                    raise exception_type("Synthetic transport failure.", request=request)

                async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
                    with self.assertRaises(EmbeddingError) as caught:
                        await embed_texts("text", client=client)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
