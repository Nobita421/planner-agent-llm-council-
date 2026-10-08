"""Model provider client supporting Groq and OpenRouter APIs."""

import asyncio
import os
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import httpx

from .config import (
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    GROQ_API_KEY,
    GROQ_API_URL,
    GROQ_MODELS_URL,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
MODEL_CATALOG_TTL_SECONDS = 300.0
_model_catalog: Optional[List[Dict[str, Any]]] = None
_model_catalog_loaded_at = 0.0

CURATED_GROQ_MODELS = [
    {
        "id": "groq/openai/gpt-oss-120b",
        "name": "Groq: OpenAI GPT OSS 120B (Flagship)",
        "provider": "Groq",
        "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "groq/qwen/qwen3.8-27b",
        "name": "Groq: Qwen 3.8 27B (Planning Specialist)",
        "provider": "Groq",
        "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "groq/openai/gpt-oss-20b",
        "name": "Groq: OpenAI GPT OSS 20B (Agile & Fast)",
        "provider": "Groq",
        "context_length": 131072,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "groq/allam-2-7b",
        "name": "Groq: ALLaM 2 7B",
        "provider": "Groq",
        "context_length": 8192,
        "pricing": {"prompt": "0", "completion": "0"},
    },
    {
        "id": "groq/canopylabs/orpheus-v1-english",
        "name": "Groq: Orpheus v1 English",
        "provider": "Groq",
        "context_length": 8192,
        "pricing": {"prompt": "0", "completion": "0"},
    },
]


def get_groq_api_key() -> Optional[str]:
    """Retrieve current Groq API key from environment or config, refreshing from .env."""
    load_dotenv(override=True)
    return os.getenv("GROQ_API_KEY") or GROQ_API_KEY


def get_openrouter_api_key() -> Optional[str]:
    """Retrieve current OpenRouter API key from environment or config, refreshing from .env."""
    load_dotenv(override=True)
    return os.getenv("OPENROUTER_API_KEY") or OPENROUTER_API_KEY


def _normalize_openrouter_model(model: Dict[str, Any]) -> Dict[str, Any]:
    model_id = str(model.get("id", "")).strip()
    name = str(model.get("name") or model_id).strip()
    provider = model_id.split("/", 1)[0] if "/" in model_id else ""
    return {
        "id": model_id,
        "name": name,
        "provider": provider,
        "context_length": model.get("context_length"),
        "pricing": model.get("pricing", {}),
    }


def _format_groq_name(raw_id: str) -> str:
    name_map = {
        "openai/gpt-oss-120b": "OpenAI GPT OSS 120B (Flagship)",
        "qwen/qwen3.8-27b": "Qwen 3.8 27B (Planning Specialist)",
        "openai/gpt-oss-20b": "OpenAI GPT OSS 20B (Agile & Fast)",
        "allam-2-7b": "ALLaM 2 7B",
        "canopylabs/orpheus-v1-english": "Orpheus v1 English",
        "canopylabs/orpheus-arabic-saudi": "Orpheus Arabic",
    }
    if raw_id in name_map:
        return f"Groq: {name_map[raw_id]}"
    clean = raw_id.replace("groq/", "").replace("-", " ").title()
    return f"Groq: {clean}"


def _normalize_groq_model(model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raw_id = str(model.get("id", "")).strip()
    if not raw_id:
        return None
    # Exclude non-chat / audio / guard / whisper models
    excluded = ("whisper", "tts", "guard", "moderation", "embedding", "distil-whisper", "prompt-guard")
    if any(pat in raw_id.lower() for pat in excluded):
        return None
    model_id = raw_id if raw_id.startswith("groq/") else f"groq/{raw_id}"
    return {
        "id": model_id,
        "name": _format_groq_name(raw_id),
        "provider": "Groq",
        "context_length": model.get("context_window", 131072),
        "pricing": {"prompt": "0", "completion": "0"},
    }


async def get_model_catalog(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Return unified model catalog (Groq + OpenRouter), refreshing when expired."""
    global _model_catalog, _model_catalog_loaded_at
    now = time.monotonic()
    if _model_catalog is not None and not force_refresh and now - _model_catalog_loaded_at < MODEL_CATALOG_TTL_SECONDS:
        return _model_catalog

    groq_models: List[Dict[str, Any]] = []
    groq_key = get_groq_api_key()

    # 1. Fetch dynamic Groq models if key is present
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    GROQ_MODELS_URL,
                    headers={"Authorization": f"Bearer {groq_key}"}
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    raw_groq_data = payload.get("data", [])
                    seen_ids = set()
                    for item in raw_groq_data:
                        norm = _normalize_groq_model(item)
                        if norm and norm["id"] not in seen_ids:
                            seen_ids.add(norm["id"])
                            groq_models.append(norm)
        except Exception as exc:
            print(f"Warning: Failed to fetch dynamic Groq model list: {exc}")

    # Fallback to curated Groq models only if dynamic fetch returned nothing
    if not groq_models:
        groq_models = list(CURATED_GROQ_MODELS)

    # Prioritize flagship and search specialist models at top
    priority_order = [
        "groq/openai/gpt-oss-120b",
        "groq/qwen/qwen3.8-27b",
        "groq/openai/gpt-oss-20b",
        "groq/allam-2-7b",
    ]
    groq_models.sort(key=lambda m: priority_order.index(m["id"]) if m["id"] in priority_order else 99)

    # 2. Fetch OpenRouter models
    openrouter_models: List[Dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(OPENROUTER_MODELS_URL)
            resp.raise_for_status()
            payload = resp.json()
            models = payload.get("data")
            if isinstance(models, list):
                for m in models:
                    norm = _normalize_openrouter_model(m)
                    if norm["id"]:
                        openrouter_models.append(norm)
    except Exception as exc:
        print(f"Warning: Failed to fetch OpenRouter model list: {exc}")
        if _model_catalog:
            openrouter_models = [m for m in _model_catalog if m.get("provider") != "Groq"]

    unified = groq_models + openrouter_models
    if unified:
        _model_catalog = unified
        _model_catalog_loaded_at = now
        return unified

    _model_catalog = list(CURATED_GROQ_MODELS)
    _model_catalog_loaded_at = now
    return _model_catalog


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 30.0,
    max_tokens: Optional[int] = 500,
) -> Optional[Dict[str, Any]]:
    """
    Query an LLM model via Groq API (for 'groq/...' models) or OpenRouter API.

    Args:
        model: Model identifier (e.g. 'groq/llama-3.3-70b-versatile' or 'openai/gpt-4o')
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        max_tokens: Maximum tokens to generate

    Returns:
        Response dict with 'content', 'reasoning_details', and 'error'
    """
    # 1. Dispatch to Groq
    if model.startswith("groq/"):
        groq_key = get_groq_api_key()
        if not groq_key:
            return {
                "content": None,
                "reasoning_details": None,
                "error": "GROQ_API_KEY is not configured in .env. Please add GROQ_API_KEY to use Groq models.",
            }

        groq_model_id = model[len("groq/"):]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {groq_key}",
        }
        payload: Dict[str, Any] = {
            "model": groq_model_id,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            timeout_cfg = httpx.Timeout(timeout=timeout, connect=10.0, read=timeout)
            async with httpx.AsyncClient(timeout=timeout_cfg) as client:
                response = await client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content")
                reasoning = message.get("reasoning_content") or message.get("reasoning_details")
                return {
                    "content": content,
                    "reasoning_details": reasoning,
                    "error": None,
                }
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:240].replace("\n", " ")
            print(f"Groq API rejected model {model} with HTTP {e.response.status_code}: {detail}")
            return {"content": None, "reasoning_details": None, "error": f"Groq HTTP {e.response.status_code}: {detail}"}
        except Exception as e:
            print(f"Groq request failed for model {model}: {e}")
            return {"content": None, "reasoning_details": None, "error": f"Groq error: {e}"}

    # 2. Dispatch to OpenRouter
    openrouter_key = get_openrouter_api_key()
    headers = {
        "Content-Type": "application/json",
    }
    if openrouter_key:
        headers["Authorization"] = f"Bearer {openrouter_key}"

    payload = {
        "model": model,
        "messages": messages,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    try:
        timeout_cfg = httpx.Timeout(timeout=timeout, connect=10.0, read=timeout)
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]

            return {
                "content": message.get("content"),
                "reasoning_details": message.get("reasoning_details"),
                "error": None,
            }
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:240].replace("\n", " ")
        print(f"OpenRouter rejected model {model} with HTTP {e.response.status_code}: {detail}")
        return {"content": None, "reasoning_details": None, "error": f"OpenRouter HTTP {e.response.status_code}: {detail}"}
    except Exception as e:
        print(f"OpenRouter request failed for model {model}: {e}")
        return {"content": None, "reasoning_details": None, "error": f"OpenRouter error: {e}"}


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """Query multiple models in parallel."""
    tasks = [query_model(model, messages) for model in models]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
