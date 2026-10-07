"""OpenRouter API client for making LLM requests."""

import httpx
import time
from typing import List, Dict, Any, Optional
from .config import OPENROUTER_API_KEY, OPENROUTER_API_URL

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
MODEL_CATALOG_TTL_SECONDS = 300.0
_model_catalog: Optional[List[Dict[str, Any]]] = None
_model_catalog_loaded_at = 0.0


def _normalize_model(model: Dict[str, Any]) -> Dict[str, Any]:
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


async def get_model_catalog(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Return the cached OpenRouter model catalog, refreshing it when expired."""
    global _model_catalog, _model_catalog_loaded_at
    now = time.monotonic()
    if _model_catalog is not None and not force_refresh and now - _model_catalog_loaded_at < MODEL_CATALOG_TTL_SECONDS:
        return _model_catalog

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(OPENROUTER_MODELS_URL)
            response.raise_for_status()
            payload = response.json()
            models = payload.get("data")
            if not isinstance(models, list):
                raise ValueError("OpenRouter model catalog response did not contain a data list")
            normalized = []
            for model in models:
                normalized_model = _normalize_model(model)
                if normalized_model["id"]:
                    normalized.append(normalized_model)
            if not normalized:
                raise ValueError("OpenRouter model catalog was empty")
            _model_catalog = normalized
            _model_catalog_loaded_at = now
            return normalized
    except Exception:
        if _model_catalog is not None:
            print("Failed to refresh OpenRouter model catalog; using stale cache.")
            return _model_catalog
        raise


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds

    Returns:
        Response dict with 'content' and optional 'reasoning_details', or None if failed
    """
    headers = {
        "Content-Type": "application/json",
    }
    if OPENROUTER_API_KEY:
        headers["Authorization"] = f"Bearer {OPENROUTER_API_KEY}"

    payload = {
        "model": model,
        "messages": messages,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()

            data = response.json()
            message = data['choices'][0]['message']

            return {
                'content': message.get('content'),
                'reasoning_details': message.get('reasoning_details')
            }

    except httpx.HTTPStatusError as e:
        detail = e.response.text[:240].replace("\n", " ")
        print(f"OpenRouter rejected model {model} with HTTP {e.response.status_code}: {detail}")
        return None
    except Exception as e:
        print(f"OpenRouter request failed for model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]]
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    import asyncio

    # Create tasks for all models
    tasks = [query_model(model, messages) for model in models]

    # Wait for all to complete
    responses = await asyncio.gather(*tasks)

    # Map models to their responses
    return {model: response for model, response in zip(models, responses)}
