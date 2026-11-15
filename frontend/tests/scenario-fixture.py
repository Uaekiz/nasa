"""Browser-test adapter: real reviewed corpus + ASGI, deliberately rejected model.

No HTTP service, database write, embedding, model download or index change.
The Node harness supplies the captured request through stdin.
"""
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "rag-service"))
import httpx
from app.main import app
from app.rag_config import RagError


async def main():
    if "--export-chat" in sys.argv:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://in-process") as client:
            capabilities = await client.get("/rag/v1/capabilities")
            with patch("app.ollama_client.generate_answer", new=AsyncMock(side_effect=RagError("INVALID_GENERATION_RESPONSE", "Explicit browser-test generation rejection."))):
                answer = await client.post("/rag/v1/answer", json={"requestId": "00000000-0000-4000-8000-000000000070",
                    "question": "Summarize FLEX test 70.", "investigationIds": ["PSI-69"]})
        assert capabilities.status_code == 200, capabilities.text
        assert answer.status_code == 200 and answer.json()["modelUsed"] is None, answer.text
        target = ROOT / "backend/target/flamescope-chat-browser.json"
        target.write_text(json.dumps({"capabilities": capabilities.json(), "answer": answer.json()}, ensure_ascii=False), encoding="utf-8")
        print("Exported real READY scope and source-chat fallback fixture; no model success claimed.")
        return
    captured = json.load(sys.stdin)
    with patch("app.scenario_narrative.generate_answer", new=AsyncMock(side_effect=RagError("MODEL_UNAVAILABLE", "Explicit browser-test fixture."))):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://in-process") as client:
            response = await client.post("/rag/v1/scenarios/evidence", json={"material": captured["params"]["material"], "params": captured["params"]})
    if response.status_code != 200:
        print(json.dumps({"status": response.status_code, "payload": response.json()}))
    else:
        print(json.dumps({"status": 200, "payload": {"requestId": "ui-real-corpus-rejected-model", "status": "EVIDENCE_RETRIEVED",
            "capturedAt": captured["capturedAt"], "params": captured["params"], "evidence": response.json()}}))


asyncio.run(main())
