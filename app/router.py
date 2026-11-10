
import json
import re

from app.config import MODELS
from app.providers import call_provider


HARD_HINTS = (
    "architecture", "debug", "optimise", "optimize", "algorithm",
    "prove", "derive", "trade-off", "tradeoff", "security review",
    "production", "multi-step", "compare approaches", "write code",
    "refactor", "root cause", "statistical"
)

MEDIUM_HINTS = (
    "explain", "summarize", "summarise", "compare",
    "分析", "pros and cons", "draft", "plan", "recommend"
)


def heuristic_route(prompt: str) -> dict:
    text = prompt.lower()
    words = len(text.split())

    hard_hits = [x for x in HARD_HINTS if x in text]
    medium_hits = [x for x in MEDIUM_HINTS if x in text]

    if hard_hits or words > 110 or "```" in prompt:
        tier = "hard"
        confidence = 0.82 if hard_hits else 0.70
        reason = "High-complexity signal(s): " + (
            ", ".join(hard_hits)
            if hard_hits
            else "long prompt/code block"
        )

    elif medium_hits or words > 35:
        tier = "medium"
        confidence = 0.72
        reason = "Moderate reasoning or synthesis signal detected"

    else:
        tier = "easy"
        confidence = 0.78
        reason = "Short, direct request with no strong complexity signals"

    return {
        "tier": tier,
        "confidence": confidence,
        "reason": reason,
        "source": "heuristic"
    }


def parse_judge_response(raw_answer: str) -> dict:
    """
    Parse the LLM judge response.

    Handles:
    - Normal JSON
    - JSON inside Markdown code fences
    - Extra text surrounding a JSON object
    """

    if not isinstance(raw_answer, str) or not raw_answer.strip():
        raise ValueError("LLM judge returned an empty response")

    cleaned = raw_answer.strip()

    # Remove Markdown JSON code fences.
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        cleaned,
        flags=re.IGNORECASE
    ).strip()

    try:
        return json.loads(cleaned)

    except json.JSONDecodeError:
        # Try extracting the first JSON object.
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

        if not match:
            raise ValueError(
                f"No valid JSON object found in judge response: {cleaned[:300]}"
            )

        return json.loads(match.group(0))


def route_prompt(prompt: str, use_llm_judge: bool = False) -> dict:
    baseline = heuristic_route(prompt)

    if not use_llm_judge:
        return baseline

    instruction = """
You are an intelligent routing classifier for an LLM gateway.

Your task is to classify the complexity of a user prompt.

Choose exactly one tier:

EASY:
- Simple factual questions
- Basic definitions
- Short transformations
- Simple calculations
- Straightforward requests

MEDIUM:
- Explanations
- Summarisation
- Comparisons
- Business analysis
- Planning
- Moderate reasoning

HARD:
- Complex reasoning
- Software architecture
- Coding and debugging
- Multi-step analysis
- Technical design
- Complex trade-off evaluation

Important:
- Judge the actual task, not just individual keywords.
- Do not classify a prompt as hard merely because it is long.
- Return ONLY valid JSON.
- Do not use Markdown code fences.

Required JSON format:

{
    "tier": "easy",
    "confidence": 0.85,
    "reason": "Short explanation of the classification"
}

The tier must be exactly easy, medium, or hard.
Confidence must be a number between 0 and 1.
"""

    try:
        result = call_provider(
            prompt=prompt,
            system_prompt=instruction,
            model=MODELS["router"],
            provider_preference=None,
            max_tokens=250,
            temperature=0
        )

        raw_answer = result["answer"]

        # Temporary debugging information.
        print("\n========== LLM JUDGE DEBUG ==========")
        print("Raw judge response:", repr(raw_answer))
        print("Judge model:", result.get("model"))
        print("Judge provider:", result.get("provider"))
        print("=====================================\n")

        parsed = parse_judge_response(raw_answer)

        tier = parsed.get("tier")
        confidence = float(parsed.get("confidence", 0.6))
        reason = str(
            parsed.get("reason", "LLM routing judge decision")
        )

        if tier not in {"easy", "medium", "hard"}:
            raise ValueError(f"Invalid tier returned by judge: {tier}")

        if not 0 <= confidence <= 1:
            raise ValueError(
                f"Invalid confidence returned by judge: {confidence}"
            )

        return {
            "tier": tier,
            "confidence": confidence,
            "reason": reason,
            "source": "llm_judge"
        }

    except Exception as exc:
        # Graceful fallback with visible debugging.
        print("\n========== LLM JUDGE ERROR ==========")
        print("Error type:", type(exc).__name__)
        print("Error:", str(exc))
        print("=====================================\n")

        return {
            **baseline,
            "reason": (
                baseline["reason"]
                + f"; LLM judge failed: {type(exc).__name__}"
            )
        }
