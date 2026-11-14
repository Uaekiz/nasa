import unittest

import httpx

from app.rag_config import RagError
from app.retrieval_checks import is_loaded, unload_for_cold_check


class ColdMeasurementTests(unittest.IsolatedAsyncioTestCase):
    async def test_an_already_unloaded_model_is_not_loaded_just_to_unload_it(self):
        methods = []

        def respond(request):
            methods.append(request.method)
            return httpx.Response(200, json={"models": []})

        async with httpx.AsyncClient(base_url="http://localhost:11434", transport=httpx.MockTransport(respond)) as client:
            await unload_for_cold_check(client, "synthetic-model")
        self.assertEqual(methods, ["GET"])

    async def test_cold_check_requires_a_verifiable_running_model_list(self):
        async with httpx.AsyncClient(base_url="http://localhost:11434", transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"unexpected": []})
        )) as client:
            with self.assertRaises(RagError) as caught:
                await is_loaded(client, "synthetic-model")
        self.assertEqual(caught.exception.code, "COLD_CHECK_UNAVAILABLE")
