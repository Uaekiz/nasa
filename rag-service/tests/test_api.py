import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.main import app


class ApiCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)

    async def test_health_is_unchanged(self):
        response = await self.client.get("/rag/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "UP"})

    @patch("app.answer_service.retrieve_for_answer", new_callable=AsyncMock)
    async def test_answer_keeps_existing_fields_and_insufficient_evidence(self, retrieve):
        retrieve.return_value = {"route": "INSUFFICIENT_EVIDENCE", "matches": [], "reason": "This question is not covered by the supplied source rows."}
        request_id = "00000000-0000-4000-8000-000000000001"
        response = await self.client.post("/rag/v1/answer", json={
            "requestId": request_id,
            "question": "What evidence is currently available for BASS-II?",
            "investigationIds": ["PSI-25"],
            "experimentIds": [],
            "analysisContext": None,
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"requestId", "answer", "status", "modelTier", "modelUsed", "sources", "warnings", "timings"})
        self.assertEqual(body["requestId"], request_id)
        self.assertEqual(body["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(body["modelTier"], "NONE")
        self.assertIsNone(body["modelUsed"])
        self.assertEqual(body["sources"], [])
        self.assertEqual(set(body["timings"]), {"retrievalMs", "generationMs", "ragTotalMs"})
        self.assertGreater(body["timings"]["ragTotalMs"], 0)


if __name__ == "__main__":
    unittest.main()
