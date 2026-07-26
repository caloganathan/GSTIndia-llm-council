"""OpenRouter API client with retries, usage accounting, and reasoning support."""

import asyncio
from typing import Any, Dict, List, Optional

import httpx

from .config import (
    MAX_RETRIES,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT,
)

# Statuses worth retrying: rate limits, timeouts, and upstream flakiness.
RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}


def _build_payload(
    model: str,
    messages: List[Dict[str, str]],
    effort: Optional[str],
    web_search: bool,
    zdr: bool = False,
    max_tokens: Optional[int] = None,
    web_max_results: Optional[int] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        # Ask OpenRouter to include token counts and dollar cost in the response
        "usage": {"include": True},
    }
    if effort and effort != "none":
        payload["reasoning"] = {"effort": effort}
    if max_tokens:
        # A cap is a cost control, not a quality control: counsel that runs to
        # 4,000 tokens where 1,200 would do is padding, not reasoning.
        payload["max_tokens"] = max_tokens
    if web_search:
        plugin: Dict[str, Any] = {"id": "web"}
        if web_max_results:
            plugin["max_results"] = web_max_results
        payload["plugins"] = [plugin]
    if zdr:
        # Route only to providers that do not retain or train on prompt data.
        payload["provider"] = {"data_collection": "deny"}
    return payload


def _extract_usage(data: Dict[str, Any]) -> Dict[str, Any]:
    usage = data.get("usage") or {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "cost": usage.get("cost"),
    }


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: Optional[float] = None,
    effort: Optional[str] = None,
    web_search: bool = False,
    zdr: bool = False,
    max_tokens: Optional[int] = None,
    web_max_results: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Query a single model via OpenRouter API.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-5.5")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds (defaults to REQUEST_TIMEOUT)
        effort: Reasoning effort ("low"/"medium"/"high"/"none"; defaults to
            REASONING_EFFORT). Stripped automatically if the model rejects it.
        web_search: Enable OpenRouter's web search plugin for this call
        zdr: Restrict routing to providers that do not retain prompt data
        max_tokens: Cap on completion length, to stop verbose padding
        web_max_results: Number of web results when web_search is on

    Returns:
        On success: {'ok': True, 'model', 'content', 'reasoning_details', 'usage'}
        On failure: {'ok': False, 'model', 'error'}
    """
    timeout = timeout if timeout is not None else REQUEST_TIMEOUT
    effort = REASONING_EFFORT if effort is None else effort

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = _build_payload(model, messages, effort, web_search, zdr,
                             max_tokens, web_max_results)
    last_error = "unknown error"

    async with httpx.AsyncClient(timeout=timeout) as client:
        attempt = 0
        while attempt <= MAX_RETRIES:
            try:
                response = await client.post(
                    OPENROUTER_API_URL, headers=headers, json=payload
                )
            except httpx.HTTPError as e:
                last_error = f"network error: {type(e).__name__}: {e}"
            else:
                if response.status_code == 200:
                    try:
                        data = response.json()
                    except ValueError as e:
                        return {"ok": False, "model": model,
                                "error": f"invalid JSON from OpenRouter: {e}"}

                    # OpenRouter can return 200 with an error body (e.g. moderation)
                    if "error" in data and "choices" not in data:
                        err = data["error"]
                        return {"ok": False, "model": model,
                                "error": f"API error: {err.get('message', err)}"}

                    try:
                        message = data["choices"][0]["message"]
                    except (KeyError, IndexError, TypeError):
                        return {"ok": False, "model": model,
                                "error": "malformed response: missing choices"}

                    content = message.get("content") or ""
                    if not content.strip():
                        return {"ok": False, "model": model,
                                "error": "model returned an empty response"}

                    return {
                        "ok": True,
                        "model": model,
                        "content": content,
                        "reasoning_details": message.get("reasoning_details"),
                        "usage": _extract_usage(data),
                    }

                # Some models reject the reasoning parameter — retry without it,
                # without consuming the retry budget.
                if response.status_code == 400 and "reasoning" in payload:
                    payload.pop("reasoning")
                    continue

                last_error = f"HTTP {response.status_code}: {response.text[:300]}"
                if response.status_code not in RETRYABLE_STATUS:
                    break

            attempt += 1
            if attempt <= MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s, ...

    print(f"Error querying model {model}: {last_error}")
    return {"ok": False, "model": model, "error": last_error}


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    web_search: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Query multiple models in parallel with the same messages.

    Returns:
        Dict mapping model identifier to its result dict (see query_model)
    """
    tasks = [query_model(model, messages, web_search=web_search) for model in models]
    responses = await asyncio.gather(*tasks)
    return {model: response for model, response in zip(models, responses)}
