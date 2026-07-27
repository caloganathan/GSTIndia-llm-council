"""
Transport to OpenRouter.

One function matters here: `query_model`. Everything in this module exists to
make that call return a *result* rather than raise, because a council is a
fan-out of a dozen concurrent calls and a single upstream hiccup must degrade
one seat, never the deliberation.

The contract, therefore, is total: every path — network failure, malformed
body, empty completion, refusal, timeout — returns a dict carrying `ok`.
Callers branch on that and nothing else.
"""

import asyncio
from typing import Any, Dict, List, Optional, Sequence

import httpx

from .config import (
    MAX_RETRIES,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT,
)

# Transient upstream conditions. Anything outside this set is the caller's
# problem (bad key, bad model id, insufficient credit) and retrying it only
# delays an error the user needs to see.
TRANSIENT_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})

# Backoff between attempts, in seconds. Short by design: these calls sit in
# front of a user watching a progress indicator.
BACKOFF_SCHEDULE = (2, 4, 8)

# Finish reasons that mean the model ran out of room rather than finished.
TRUNCATION_REASONS = frozenset({"length", "max_tokens", "MAX_TOKENS"})

# When a reasoning model spends its entire allowance thinking and has nothing
# left to answer with, retry once with this much more room. A ceiling costs
# nothing until it is used — billing is per token generated, not per token
# permitted — so the headroom is close to free.
STARVED_RETRY_MULTIPLIER = 3


def _failed(model: str, reason: str) -> Dict[str, Any]:
    return {"ok": False, "model": model, "error": reason}


def _succeeded(model: str, message: Dict[str, Any],
               body: Dict[str, Any]) -> Dict[str, Any]:
    meter = body.get("usage") or {}
    return {
        "ok": True,
        "model": model,
        "content": message.get("content") or "",
        "reasoning_details": message.get("reasoning_details"),
        "usage": {
            "prompt_tokens": meter.get("prompt_tokens"),
            "completion_tokens": meter.get("completion_tokens"),
            "total_tokens": meter.get("total_tokens"),
            "cost": meter.get("cost"),
        },
    }


def _compose_request(
    model: str,
    messages: Sequence[Dict[str, str]],
    effort: Optional[str],
    web_search: bool,
    zdr: bool,
    max_tokens: Optional[int],
    web_max_results: Optional[int],
) -> Dict[str, Any]:
    """Assemble the request body. Optional features are added only when asked
    for — an unrecognised key is a 400 on some providers."""
    body: Dict[str, Any] = {
        "model": model,
        "messages": list(messages),
        # Token counts and dollar cost come back on the response, which is the
        # only way the cost line shown to the user can be truthful.
        "usage": {"include": True},
    }

    if effort and effort != "none":
        body["reasoning"] = {"effort": effort}

    if max_tokens:
        # A ceiling is cost control, not quality control. Counsel that runs to
        # four thousand tokens where twelve hundred would do is padding.
        body["max_tokens"] = max_tokens

    if web_search:
        plugin: Dict[str, Any] = {"id": "web"}
        if web_max_results:
            plugin["max_results"] = web_max_results
        body["plugins"] = [plugin]

    if zdr:
        # Confine routing to providers that neither retain nor train on the
        # prompt. Client facts travel under this flag or not at all.
        body["provider"] = {"data_collection": "deny"}

    return body


def _read_completion(model: str, response: httpx.Response) -> Dict[str, Any]:
    """
    Turn a 200 into a result.

    A 200 is not success. OpenRouter returns 200 with an error object for
    moderation refusals, and 200 with an empty string in two quite different
    situations that must not be conflated:

      * the provider simply gave up — transient, worth another attempt;
      * the model exhausted its token allowance while reasoning and had
        nothing left to answer with.

    The second is the dangerous one, because it looks like flakiness and is in
    fact a configuration fault: `max_tokens` bounds the WHOLE completion, and
    on a reasoning model the thinking is charged against it first. A high
    effort setting under a tight ceiling produces a model that thinks until it
    runs out of room and returns nothing at all. Retrying that identically
    fails identically, so it is detected here and named.
    """
    try:
        body = response.json()
    except ValueError as exc:
        return _failed(model, f"response was not JSON: {exc}")

    if not isinstance(body, dict):
        return _failed(model, "response was not a JSON object")

    if "choices" not in body and "error" in body:
        detail = body["error"]
        if isinstance(detail, dict):
            detail = detail.get("message") or detail
        return _failed(model, f"provider refused: {detail}")

    try:
        choice = body["choices"][0]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        return _failed(model, "response carried no completion")

    if (message.get("content") or "").strip():
        return _succeeded(model, message, body)

    # Empty. Work out which kind.
    finish = choice.get("finish_reason") or choice.get("native_finish_reason")
    spent = (body.get("usage") or {}).get("completion_tokens")

    if finish in TRUNCATION_REASONS:
        outcome = _failed(model, (
            "the model used its entire output allowance while reasoning and "
            f"produced no answer (finish_reason={finish}"
            f"{f', {spent} tokens spent' if spent else ''}). Raise the token "
            "ceiling for this role, or lower its reasoning effort."
        ))
        outcome["_starved"] = True
        return outcome

    outcome = _failed(model, "provider returned an empty completion")
    outcome["_empty"] = True
    return outcome


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
    Put one prompt to one model and return what came back.

    Never raises. On success the result carries `content`, `reasoning_details`
    and `usage`; on failure it carries `error`. Both carry `ok` and `model`.

    Args:
        model: OpenRouter identifier, e.g. "openai/gpt-5.5"
        messages: chat messages, each with 'role' and 'content'
        timeout: seconds for the whole request; falls back to REQUEST_TIMEOUT
        effort: reasoning budget — low, medium, high or none. Falls back to
            REASONING_EFFORT. Dropped automatically if the provider rejects it.
        web_search: attach OpenRouter's web plugin to this call
        zdr: restrict routing to providers that do not retain prompt data
        max_tokens: ceiling on completion length
        web_max_results: number of search results when web_search is set
    """
    timeout = REQUEST_TIMEOUT if timeout is None else timeout
    effort = REASONING_EFFORT if effort is None else effort

    credentials = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    body = _compose_request(model, messages, effort, web_search, zdr,
                            max_tokens, web_max_results)

    setback = "no attempt completed"
    attempts_spent = 0
    headroom_granted = False

    async with httpx.AsyncClient(timeout=timeout) as client:
        while attempts_spent <= MAX_RETRIES:
            try:
                response = await client.post(
                    OPENROUTER_API_URL, headers=credentials, json=body
                )
            except httpx.HTTPError as exc:
                setback = f"network error: {type(exc).__name__}: {exc}"
            else:
                if response.status_code == 200:
                    outcome = _read_completion(model, response)
                    if outcome["ok"]:
                        return outcome

                    # The model thought until it ran out of room. Grant it
                    # more and let it answer — once. This is a correction, not
                    # a retry, so it does not spend the allowance either.
                    if (outcome.get("_starved") and not headroom_granted
                            and body.get("max_tokens")):
                        headroom_granted = True
                        body["max_tokens"] *= STARVED_RETRY_MULTIPLIER
                        print(f"Model {model} exhausted its allowance while "
                              f"reasoning; retrying with "
                              f"{body['max_tokens']} tokens")
                        continue

                    # A bare empty completion is usually the provider
                    # stumbling, so it is worth one more attempt on the
                    # ordinary schedule.
                    if outcome.get("_empty"):
                        setback = outcome["error"]
                    else:
                        return outcome

                # Not every model accepts a reasoning budget. Shed the
                # parameter and go again — this is a negotiation, not a
                # failure, so it does not spend the retry allowance.
                elif response.status_code == 400 and "reasoning" in body:
                    body.pop("reasoning")
                    continue

                else:
                    setback = (f"HTTP {response.status_code}: "
                               f"{response.text[:300]}")
                    if response.status_code not in TRANSIENT_STATUSES:
                        break

            if attempts_spent < len(BACKOFF_SCHEDULE) and attempts_spent < MAX_RETRIES:
                await asyncio.sleep(BACKOFF_SCHEDULE[attempts_spent])
            attempts_spent += 1

    print(f"Model {model} did not answer: {setback}")
    return _failed(model, setback)


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    web_search: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Put the same prompt to several models at once.

    Returns a mapping of model identifier to its individual result. Because
    `query_model` never raises, a failing seat appears as a failed result
    beside its successful peers rather than collapsing the gather.
    """
    seats = [
        query_model(model, messages, web_search=web_search) for model in models
    ]
    return dict(zip(models, await asyncio.gather(*seats)))
