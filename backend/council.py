"""3-stage LLM Council orchestration."""

import asyncio
import re
from collections import defaultdict
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from .config import CHAIRMAN_MODEL, COUNCIL_MODELS, HISTORY_MAX_TURNS, TITLE_MODEL
from .openrouter import query_model, query_models_parallel


def build_history_messages(
    prior_messages: List[Dict[str, Any]],
    max_turns: int = HISTORY_MAX_TURNS,
) -> List[Dict[str, str]]:
    """
    Convert stored conversation messages into chat messages usable as context.

    User messages pass through; assistant messages are represented by their
    final (Stage 3) answer. Only the most recent `max_turns` exchanges are kept
    to bound token usage.
    """
    history: List[Dict[str, str]] = []
    for msg in prior_messages:
        if msg.get("role") == "user" and msg.get("content"):
            history.append({"role": "user", "content": msg["content"]})
        elif msg.get("role") == "assistant":
            final = (msg.get("stage3") or {}).get("response")
            if final:
                history.append({"role": "assistant", "content": final})
    # Keep the last N user/assistant pairs
    return history[-(max_turns * 2):]


def format_history_snippet(
    history: List[Dict[str, str]],
    max_turns: int = 3,
    max_chars: int = 1500,
) -> str:
    """Compact text rendering of recent history for inclusion inside prompts."""
    recent = history[-(max_turns * 2):]
    if not recent:
        return ""
    lines = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Council answer"
        content = msg["content"]
        if len(content) > max_chars:
            content = content[:max_chars] + " [...truncated]"
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


async def stage1_collect_responses(
    user_query: str,
    history: Optional[List[Dict[str, str]]] = None,
    web_search: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """
    Stage 1: Collect individual responses from all council models.

    Returns:
        Tuple of (successful results, failures). Each result has
        'model', 'response', 'usage'; each failure has 'model', 'error'.
    """
    messages = list(history or []) + [{"role": "user", "content": user_query}]

    responses = await query_models_parallel(
        COUNCIL_MODELS, messages, web_search=web_search
    )

    stage1_results = []
    failures = []
    for model, response in responses.items():
        if response.get("ok"):
            stage1_results.append({
                "model": model,
                "response": response["content"],
                "usage": response.get("usage"),
            })
        else:
            failures.append({"model": model, "error": response.get("error", "unknown")})

    return stage1_results, failures


def _build_ranking_prompt(
    user_query: str,
    labeled_responses: List[Tuple[str, str]],
    history_snippet: str,
) -> str:
    responses_text = "\n\n".join(
        f"Response {label}:\n{text}" for label, text in labeled_responses
    )
    context_block = (
        f"For context, here is the recent conversation that led to this "
        f"question:\n\n{history_snippet}\n\n"
        if history_snippet else ""
    )
    labels_list = ", ".join(f"Response {label}" for label, _ in labeled_responses)

    return f"""You are evaluating different responses to the following question:

{context_block}Question: {user_query}

Here are the responses from different models (anonymized):

{responses_text}

Your task:
1. First, evaluate each response individually. For each response, assess factual accuracy, depth of insight, completeness, and practical usefulness. Explain what it does well and what it does poorly, and flag any errors or unsupported claims.
2. Then, at the very end of your response, provide a final ranking of ALL of these responses: {labels_list}.

IMPORTANT: Your final ranking MUST be formatted EXACTLY as follows:
- Start with the line "FINAL RANKING:" (all caps, with colon)
- Then list the responses from best to worst as a numbered list
- Each line should be: number, period, space, then ONLY the response label (e.g., "1. Response A")
- Include every label exactly once
- Do not add any other text or explanations in the ranking section

Example of the correct format for the end of your response:

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Now provide your evaluation and ranking:"""


async def stage2_collect_rankings(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    history: Optional[List[Dict[str, str]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[Dict[str, str]]]:
    """
    Stage 2: Each model ranks the anonymized responses of its PEERS.

    A model never sees or ranks its own response, which removes
    self-preference bias from the aggregate.

    Returns:
        Tuple of (rankings list, label_to_model mapping, failures list)
    """
    labels = [chr(65 + i) for i in range(len(stage1_results))]  # A, B, C, ...

    label_to_model = {
        f"Response {label}": result["model"]
        for label, result in zip(labels, stage1_results)
    }
    model_to_label = {v: k for k, v in label_to_model.items()}

    history_snippet = format_history_snippet(history or [])

    # Build one prompt per ranker, excluding its own response.
    # Tuples: (ranker model, its own label if any, labels it will see, prompt)
    ranker_prompts: List[Tuple[str, Optional[str], List[str], str]] = []
    for ranker in COUNCIL_MODELS:
        own_label = model_to_label.get(ranker)
        shown = [
            (label, result["response"])
            for label, result in zip(labels, stage1_results)
            if f"Response {label}" != own_label
        ]
        if len(shown) < 2:
            continue  # nothing meaningful to rank
        valid_labels = [f"Response {label}" for label, _ in shown]
        prompt = _build_ranking_prompt(user_query, shown, history_snippet)
        ranker_prompts.append((ranker, own_label, valid_labels, prompt))

    tasks = [
        query_model(ranker, [{"role": "user", "content": prompt}])
        for ranker, _, _, prompt in ranker_prompts
    ]
    responses = await asyncio.gather(*tasks) if tasks else []

    stage2_results = []
    failures = []
    for (ranker, own_label, valid_labels, _), response in zip(ranker_prompts, responses):
        if response.get("ok"):
            full_text = response["content"]
            parsed = parse_ranking_from_text(full_text, valid_labels)
            stage2_results.append({
                "model": ranker,
                "ranking": full_text,
                "parsed_ranking": parsed,
                "own_label": own_label,
                "parse_complete": len(parsed) == len(valid_labels),
                "usage": response.get("usage"),
            })
        else:
            failures.append({"model": ranker, "error": response.get("error", "unknown")})

    return stage2_results, label_to_model, failures


async def stage3_synthesize_final(
    user_query: str,
    stage1_results: List[Dict[str, Any]],
    stage2_results: List[Dict[str, Any]],
    label_to_model: Optional[Dict[str, str]] = None,
    aggregate_rankings: Optional[List[Dict[str, Any]]] = None,
    history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Stage 3: Chairman synthesizes final response.

    The chairman receives the individual responses, the peer evaluations, the
    label→model mapping (so it can connect verdicts to answers), and the
    computed aggregate ranking.
    """
    model_to_label = {v: k for k, v in (label_to_model or {}).items()}

    stage1_text = "\n\n".join(
        f"[{model_to_label.get(result['model'], 'unlabeled')}] "
        f"Model: {result['model']}\nResponse: {result['response']}"
        for result in stage1_results
    )

    review_section = ""
    if stage2_results:
        mapping_text = "\n".join(
            f"- {label} = {model}" for label, model in (label_to_model or {}).items()
        )
        stage2_text = "\n\n".join(
            f"Reviewer: {result['model']}\nEvaluation:\n{result['ranking']}"
            for result in stage2_results
        )
        aggregate_text = "\n".join(
            f"{i + 1}. {agg['model']} (normalized score {agg['score']}, "
            f"{agg['rankings_count']} peer reviews)"
            for i, agg in enumerate(aggregate_rankings or [])
        ) or "No aggregate ranking could be computed."

        review_section = f"""
STAGE 2 - Peer Reviews (each reviewer saw only anonymized responses, and never its own):
{stage2_text}

Label-to-model mapping (reviewers referred to responses by these labels):
{mapping_text}

Peer-review consensus, best to worst (lower score is better):
{aggregate_text}
"""

    context_block = ""
    history_snippet = format_history_snippet(history or [], max_turns=HISTORY_MAX_TURNS)
    if history_snippet:
        context_block = f"""
Conversation so far (for context — the question below is a continuation):
{history_snippet}
"""

    chairman_prompt = f"""You are the Chairman of an LLM Council. Multiple AI models have provided responses to a user's question{', and then anonymously reviewed and ranked each other’s responses' if stage2_results else ''}.
{context_block}
Original Question: {user_query}

STAGE 1 - Individual Responses:
{stage1_text}
{review_section}
Your task as Chairman is to synthesize all of this into the single best possible answer to the user's original question. Guidelines:
- Weight the peer-review consensus, but exercise independent judgment — if the top-ranked response contains an error a reviewer caught, correct it.
- Where the models disagree on substance, resolve the disagreement explicitly rather than averaging over it, and say which position you adopted and why.
- Preserve concrete, actionable detail from the strongest responses; do not water the answer down to generic advice.
- If material uncertainty remains (e.g., the council disagreed and neither side is verifiable), state it plainly.
- Answer the user directly — do not describe the council process in your answer.

Provide the final answer now:"""

    messages = list(history or []) + [{"role": "user", "content": chairman_prompt}]

    response = await query_model(CHAIRMAN_MODEL, messages)

    if not response.get("ok"):
        return {
            "model": CHAIRMAN_MODEL,
            "response": f"Error: Unable to generate final synthesis "
                        f"({response.get('error', 'unknown error')}). "
                        f"Individual responses in Stage 1 are still available above.",
            "error": True,
        }

    return {
        "model": CHAIRMAN_MODEL,
        "response": response["content"],
        "usage": response.get("usage"),
    }


def parse_ranking_from_text(
    ranking_text: str,
    valid_labels: Optional[List[str]] = None,
) -> List[str]:
    """
    Parse the FINAL RANKING section from the model's response.

    Deduplicates labels (first occurrence wins) and, when valid_labels is
    given, drops any label that wasn't actually in the ranked set — so stray
    "Response X" mentions in prose can't corrupt the ranking.
    """
    section = ranking_text
    if "FINAL RANKING:" in ranking_text:
        # Use the LAST occurrence: models sometimes restate the header in prose
        section = ranking_text.rsplit("FINAL RANKING:", 1)[1]

    # Prefer the strict numbered-list format
    matches = re.findall(r"\d+\.\s*(Response [A-Z])", section)
    if not matches:
        # Fallback: any "Response X" mentions in order
        matches = re.findall(r"Response [A-Z]", section)

    valid = set(valid_labels) if valid_labels is not None else None
    seen = set()
    ordered = []
    for label in matches:
        if label in seen:
            continue
        if valid is not None and label not in valid:
            continue
        seen.add(label)
        ordered.append(label)
    return ordered


def calculate_aggregate_rankings(
    stage2_results: List[Dict[str, Any]],
    label_to_model: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Calculate aggregate rankings across all peer reviews.

    Because each reviewer ranks a different subset (its own response is
    excluded), raw positions aren't directly comparable. Positions are
    normalized to [0, 1] within each review (0 = ranked best, 1 = ranked
    worst) and averaged.
    """
    scores = defaultdict(list)
    positions = defaultdict(list)

    for entry in stage2_results:
        parsed = entry.get("parsed_ranking") or []
        n = len(parsed)
        if n == 0:
            continue
        for pos, label in enumerate(parsed, start=1):
            model = label_to_model.get(label)
            if model is None:
                continue
            positions[model].append(pos)
            scores[model].append((pos - 1) / (n - 1) if n > 1 else 0.5)

    aggregate = []
    for model, model_scores in scores.items():
        aggregate.append({
            "model": model,
            "score": round(sum(model_scores) / len(model_scores), 3),
            "average_rank": round(sum(positions[model]) / len(positions[model]), 2),
            "rankings_count": len(model_scores),
        })

    aggregate.sort(key=lambda x: x["score"])
    return aggregate


def _sum_usage(*usage_lists: List[Optional[Dict[str, Any]]]) -> Dict[str, Any]:
    """Aggregate token counts and cost across stages (missing values ignored)."""
    total_tokens = 0
    total_cost = 0.0
    for usages in usage_lists:
        for usage in usages:
            if not usage:
                continue
            total_tokens += usage.get("total_tokens") or 0
            total_cost += usage.get("cost") or 0.0
    return {"total_tokens": total_tokens, "total_cost": round(total_cost, 6)}


async def generate_conversation_title(user_query: str) -> str:
    """Generate a short title for a conversation from its first message."""
    title_prompt = f"""Generate a very short title (3-5 words maximum) that summarizes the following question.
The title should be concise and descriptive. Do not use quotes or punctuation in the title.

Question: {user_query}

Title:"""

    messages = [{"role": "user", "content": title_prompt}]
    response = await query_model(TITLE_MODEL, messages, timeout=30.0, effort="none")

    if not response.get("ok"):
        return "New Conversation"

    title = response.get("content", "New Conversation").strip().strip("\"'")
    if len(title) > 50:
        title = title[:47] + "..."
    return title or "New Conversation"


async def run_council_stream(
    user_query: str,
    prior_messages: Optional[List[Dict[str, Any]]] = None,
    mode: str = "full",
    web_search: bool = False,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Run the council process, yielding an event dict as each stage progresses.

    Modes:
        "full": Stage 1 → anonymized peer review → chairman synthesis
        "quick": Stage 1 → chairman synthesis (skips peer review)

    Events: stage1_start, stage1_complete, stage2_start, stage2_complete,
    stage3_start, stage3_complete, summary. The summary event carries the
    complete metadata (mapping, aggregates, failures, usage).
    """
    history = build_history_messages(prior_messages or [])

    # Stage 1: individual responses
    yield {"type": "stage1_start"}
    stage1_results, stage1_failures = await stage1_collect_responses(
        user_query, history=history, web_search=web_search
    )
    yield {"type": "stage1_complete", "data": stage1_results,
           "failures": stage1_failures}

    if not stage1_results:
        details = "; ".join(f"{f['model']}: {f['error']}" for f in stage1_failures)
        yield {
            "type": "summary",
            "data": {
                "stage1": [], "stage2": [],
                "stage3": {"model": "error",
                           "response": f"All council models failed to respond. {details}"},
            },
            "metadata": {"failures": {"stage1": stage1_failures, "stage2": []},
                         "mode": mode, "web_search": web_search},
        }
        return

    # Stage 2: anonymized peer review (full mode only, needs >= 2 responses)
    stage2_results: List[Dict[str, Any]] = []
    stage2_failures: List[Dict[str, str]] = []
    label_to_model: Dict[str, str] = {}
    aggregate_rankings: List[Dict[str, Any]] = []

    if mode != "quick" and len(stage1_results) >= 2:
        yield {"type": "stage2_start"}
        stage2_results, label_to_model, stage2_failures = await stage2_collect_rankings(
            user_query, stage1_results, history=history
        )
        aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
        yield {
            "type": "stage2_complete",
            "data": stage2_results,
            "failures": stage2_failures,
            "metadata": {"label_to_model": label_to_model,
                         "aggregate_rankings": aggregate_rankings},
        }

    # Stage 3: chairman synthesis
    yield {"type": "stage3_start"}
    stage3_result = await stage3_synthesize_final(
        user_query, stage1_results, stage2_results,
        label_to_model=label_to_model,
        aggregate_rankings=aggregate_rankings,
        history=history,
    )
    yield {"type": "stage3_complete", "data": stage3_result}

    usage = _sum_usage(
        [r.get("usage") for r in stage1_results],
        [r.get("usage") for r in stage2_results],
        [stage3_result.get("usage")],
    )

    metadata = {
        "label_to_model": label_to_model,
        "aggregate_rankings": aggregate_rankings,
        "failures": {"stage1": stage1_failures, "stage2": stage2_failures},
        "usage": usage,
        "mode": mode,
        "web_search": web_search,
    }

    yield {
        "type": "summary",
        "data": {"stage1": stage1_results, "stage2": stage2_results,
                 "stage3": stage3_result},
        "metadata": metadata,
    }


async def run_full_council(
    user_query: str,
    prior_messages: Optional[List[Dict[str, Any]]] = None,
    mode: str = "full",
    web_search: bool = False,
) -> Tuple[List, List, Dict, Dict]:
    """
    Run the complete council process non-streaming.

    Returns:
        Tuple of (stage1_results, stage2_results, stage3_result, metadata)
    """
    stage1: List = []
    stage2: List = []
    stage3: Dict = {}
    metadata: Dict = {}

    async for event in run_council_stream(
        user_query, prior_messages=prior_messages, mode=mode, web_search=web_search
    ):
        if event["type"] == "summary":
            stage1 = event["data"]["stage1"]
            stage2 = event["data"]["stage2"]
            stage3 = event["data"]["stage3"]
            metadata = event.get("metadata", {})

    return stage1, stage2, stage3, metadata
