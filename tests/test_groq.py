"""Tests for Groq model integration, catalog generation, and pipeline dispatch."""

import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from httpx import AsyncClient, ASGITransport, Response

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.main import app
from backend.openrouter import get_model_catalog, query_model, get_groq_api_key


@pytest.mark.asyncio
async def test_groq_models_in_catalog():
    """Verify that Groq models appear in the unified model catalog with Free pricing."""
    catalog = await get_model_catalog(force_refresh=True)
    groq_models = [m for m in catalog if m.get("provider") == "Groq"]

    assert len(groq_models) >= 2
    model_ids = {m["id"] for m in groq_models}
    assert "groq/openai/gpt-oss-120b" in model_ids
    assert "groq/qwen/qwen3.8-27b" in model_ids

    for m in groq_models:
        assert m["pricing"]["prompt"] == "0"
        assert m["pricing"]["completion"] == "0"


@pytest.mark.asyncio
async def test_api_models_endpoint():
    """Test the /api/models endpoint returns unified catalog and proper defaults."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()

        assert "models" in data
        assert "defaults" in data
        defaults = data["defaults"]
        assert "optimal" in defaults
        assert "satisficing" in defaults
        assert "agile" in defaults
        assert "judge" in defaults


@pytest.mark.asyncio
async def test_groq_query_model_missing_key():
    """Verify that calling a groq/ model without an API key returns a clear error."""
    with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
        with patch("backend.openrouter.get_groq_api_key", return_value=None):
            result = await query_model("groq/openai/gpt-oss-120b", [{"role": "user", "content": "hi"}])
            assert result is not None
            assert result["content"] is None
            assert "GROQ_API_KEY is not configured" in result["error"]


@pytest.mark.asyncio
async def test_groq_query_model_success():
    """Verify query_model dispatches correctly to Groq's completions endpoint."""
    fake_groq_response = {
        "id": "chatcmpl-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "### Strategy Proposal: A* with LM-Cut\nOptimal plan selected.",
                }
            }
        ]
    }

    mock_resp = MagicMock(spec=Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_groq_response
    mock_resp.raise_for_status = MagicMock()

    with patch("backend.openrouter.get_groq_api_key", return_value="gsk_mock_test_key"):
        with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
            res = await query_model(
                "groq/openai/gpt-oss-120b",
                [{"role": "user", "content": "Analyze planning problem"}],
                timeout=15.0,
                max_tokens=400,
            )

            assert res is not None
            assert res["content"] is not None
            assert "Strategy Proposal" in res["content"]
            assert res["error"] is None

            # Verify POST arguments sent to Groq
            call_args, call_kwargs = mock_post.call_args
            assert call_args[0] == "https://api.groq.com/openai/v1/chat/completions"
            assert "Authorization" in call_kwargs["headers"]
            assert call_kwargs["headers"]["Authorization"] == "Bearer gsk_mock_test_key"
            assert call_kwargs["json"]["model"] == "openai/gpt-oss-120b"
            assert call_kwargs["json"]["max_tokens"] == 400


@pytest.mark.asyncio
async def test_solve_pddl_accepts_groq_models():
    """Verify /api/solve-pddl validates and accepts groq/ model overrides."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "domain_pddl": "(define (domain d) (:predicates (p)) (:action a :effect (p)))",
            "problem_pddl": "(define (problem p) (:domain d) (:goal (p)))",
            "user_constraints": {
                "models": {
                    "optimal": "groq/openai/gpt-oss-120b",
                    "satisficing": "groq/qwen/qwen3.8-27b",
                    "agile": "groq/openai/gpt-oss-20b",
                    "judge": "groq/openai/gpt-oss-120b",
                }
            }
        }
        resp = await client.post("/api/solve-pddl", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "debate" in data
        assert "validation" in data

        # Ensure the custom Groq models were recorded in Stage 1
        stage1_agents = {agent["role"]: agent["model"] for agent in data["debate"]["stage1"]}
        assert stage1_agents["optimal"] == "groq/openai/gpt-oss-120b"
        assert stage1_agents["satisficing"] == "groq/qwen/qwen3.8-27b"
        assert stage1_agents["agile"] == "groq/openai/gpt-oss-20b"
