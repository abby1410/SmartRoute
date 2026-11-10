
import os
import csv
import json
import time
import argparse
import re
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv(
    "SMARTROUTE_API_URL",
    "http://127.0.0.1:8000"
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

JUDGE_MODEL = os.getenv(
    "JUDGE_MODEL",
    "openai/gpt-oss-120b"
)

GROQ_BASE_URL = os.getenv(
    "GROQ_BASE_URL",
    "https://api.groq.com/openai/v1"
)

REQUEST_DELAY_SECONDS = float(
    os.getenv("EVAL_REQUEST_DELAY_SECONDS", "1.5")
)

BENCHMARK_FILE = Path("evaluation/benchmark.csv")

RESULTS_DIR = Path("evaluation/results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

DETAIL_FILE = RESULTS_DIR / "detail.csv"
SUMMARY_FILE = RESULTS_DIR / "summary.csv"


# --------------------------------------------------
# 1. Gateway request with retry and backoff
# --------------------------------------------------

def post_with_retry(url, payload, max_attempts=4):

    for attempt in range(max_attempts):

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=120
            )

            if response.status_code in (429, 502, 503, 504):

                if attempt == max_attempts - 1:
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")

                try:
                    if retry_after:
                        delay = float(retry_after)
                    elif response.status_code == 429:
                        delay = 60
                    else:
                        delay = 3 * (2 ** attempt)

                except ValueError:
                    delay = (
                        60
                        if response.status_code == 429
                        else 3 * (2 ** attempt)
                    )

                print(
                    f"Gateway returned {response.status_code}. "
                    f"Retrying in {delay:.1f} seconds..."
                )

                time.sleep(delay)
                continue

            response.raise_for_status()
            return response

        except requests.HTTPError:
            raise

        except requests.RequestException as error:

            if attempt == max_attempts - 1:
                raise

            delay = 3 * (2 ** attempt)

            print(
                f"Network error: {error}. "
                f"Retrying in {delay} seconds..."
            )

            time.sleep(delay)

    raise RuntimeError(
        "Request failed after all retry attempts"
    )


# --------------------------------------------------
# 2. LLM-as-a-judge evaluation
# --------------------------------------------------

def judge_answer(prompt, reference, candidate):

    if not GROQ_API_KEY:
        return None, "Missing GROQ_API_KEY"

    judge_prompt = f"""
You are evaluating an AI assistant response.

User question:
{prompt}

Reference answer:
{reference}

Candidate answer:
{candidate}

Score the candidate from 1 to 5:

1 = Incorrect or irrelevant
2 = Mostly incorrect
3 = Partially correct
4 = Mostly correct
5 = Fully correct and useful

Return ONLY valid JSON:

{{
    "score": 1,
    "reason": "Short explanation"
}}
"""

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": JUDGE_MODEL,
        "messages": [
            {
                "role": "user",
                "content": judge_prompt
            }
        ],
        "temperature": 0,
        "max_tokens": 300,
        "response_format": {
            "type": "json_object"
        }
    }

    for attempt in range(4):

        try:

            time.sleep(2)

            response = requests.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code == 429:

                delay = 5 * (2 ** attempt)

                print(
                    f"Judge rate limited. "
                    f"Waiting {delay}s..."
                )

                time.sleep(delay)
                continue

            response.raise_for_status()

            content = (
                response.json()["choices"][0]
                ["message"]["content"]
            )

            content = content.strip()

            content = re.sub(
                r"^```(?:json)?",
                "",
                content
            )

            content = re.sub(
                r"```$",
                "",
                content
            ).strip()

            match = re.search(
                r"\{.*\}",
                content,
                re.DOTALL
            )

            if not match:
                return None, "Judge did not return valid JSON"

            result = json.loads(match.group(0))

            score = float(result["score"])
            reason = str(result.get("reason", ""))

            return score, reason

        except Exception as error:

            if attempt == 3:
                return None, str(error)

            time.sleep(3 * (2 ** attempt))

    return None, "Judge failed after retries"


# --------------------------------------------------
# 3. Load benchmark dataset
# --------------------------------------------------

def load_benchmark(limit=None):

    with open(
        BENCHMARK_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        rows = list(csv.DictReader(file))

    if limit:
        rows = rows[:limit]

    return rows


# --------------------------------------------------
# 4. Main evaluation loop
# --------------------------------------------------

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None
    )

    parser.add_argument(
        "--no-judge",
        action="store_true"
    )

    parser.add_argument(
        "--strategies",
        nargs="+",
        default=["auto", "cheapest", "strongest"]
    )

    args = parser.parse_args()

    benchmark = load_benchmark(args.limit)

    print(
        f"Loaded {len(benchmark)} benchmark prompts"
    )

    print(
        f"Strategies: {args.strategies}"
    )

    print(
        f"Request delay: {REQUEST_DELAY_SECONDS}s"
    )

    all_results = []

    for index, item in enumerate(
        benchmark,
        start=1
    ):

        prompt_id = item.get("id", index)

        prompt = item["prompt"]

        reference = item.get(
            "reference_answer",
            item.get("reference", "")
        )

        expected_tier = item.get(
            "expected_tier",
            ""
        )

        for strategy in args.strategies:

            print(
                f"\nPrompt {index}/{len(benchmark)} | "
                f"Strategy: {strategy}"
            )

            result = {

                "prompt_id": prompt_id,
                "strategy": strategy,
                "expected_tier": expected_tier,

                "success": False,

                "quality_score": None,
                "judge_reason": "",

                "latency_ms": None,
                "estimated_cost_usd": None,

                "prompt_tokens": None,
                "completion_tokens": None,

                "actual_tier": "",
                "route_accuracy": None,

                "error": "",
                "judge_error": ""
            }

            try:

                start_time = time.time()

                response = post_with_retry(
                    f"{API_URL}/chat",
                    {
                        "prompt": prompt,

                        "system_prompt": (
                            "You are a helpful and accurate assistant."
                        ),

                        "strategy": strategy,

                        "use_llm_judge": False,
                        "use_cache": False
                    }
                )

                elapsed_ms = (
                    time.time() - start_time
                ) * 1000

                data = response.json()

                result["success"] = True

                result["latency_ms"] = elapsed_ms

                result["estimated_cost_usd"] = data.get(
                    "estimated_cost",
                    data.get("estimated_cost_usd")
                )

                result["prompt_tokens"] = data.get(
                    "input_tokens",
                    data.get("prompt_tokens")
                )

                result["completion_tokens"] = data.get(
                    "output_tokens",
                    data.get("completion_tokens")
                )

                # IMPORTANT:
                # Top-level tier is the final selected tier
                # after strategy overrides.
                #
                # route.tier is the original router decision.
                # Do not use it as the final tier.

                actual_tier = data.get("tier", "")

                if not actual_tier:

                    route = data.get("route", {})

                    if isinstance(route, dict):

                        actual_tier = (
                            route.get("final_tier")
                            or route.get("tier", "")
                        )

                result["actual_tier"] = actual_tier

                # Route accuracy is measured only for auto.
                # Cheapest and strongest intentionally override
                # the initial router decision.

                if (
                    strategy == "auto"
                    and expected_tier
                ):

                    result["route_accuracy"] = (
                        str(actual_tier).lower()
                        == str(expected_tier).lower()
                    )

                answer = (
                    data.get("answer")
                    or data.get("response")
                    or data.get("content")
                    or ""
                )

                if not answer:
                    answer = str(data)

                print(
                    f"Success | "
                    f"Tier: {actual_tier} | "
                    f"Latency: {elapsed_ms:.0f}ms"
                )

                # Run LLM judge only when enabled.

                if not args.no_judge:

                    score, reason = judge_answer(
                        prompt,
                        reference,
                        answer
                    )

                    result["quality_score"] = score

                    result["judge_reason"] = reason

                    if score is None:
                        result["judge_error"] = reason

                    print(
                        f"Judge score: {score} | "
                        f"{reason}"
                    )

            except Exception as error:

                result["error"] = str(error)

                print(
                    f"Request failed: {error}"
                )

            all_results.append(result)

            # Pace requests to respect gateway rate limits.

            time.sleep(REQUEST_DELAY_SECONDS)

    # --------------------------------------------------
    # 5. Save detailed results
    # --------------------------------------------------

    if all_results:

        with open(
            DETAIL_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=all_results[0].keys()
            )

            writer.writeheader()
            writer.writerows(all_results)

    # --------------------------------------------------
    # 6. Generate strategy-level summary
    # --------------------------------------------------

    summary = []

    for strategy in args.strategies:

        rows = [
            row
            for row in all_results
            if row["strategy"] == strategy
        ]

        successful = [
            row
            for row in rows
            if row["success"]
        ]

        scored = [
            row
            for row in successful
            if row["quality_score"] is not None
        ]

        latencies = [
            row["latency_ms"]
            for row in successful
            if row["latency_ms"] is not None
        ]

        costs = [
            row["estimated_cost_usd"]
            for row in successful
            if row["estimated_cost_usd"] is not None
        ]

        route_checks = [
            row["route_accuracy"]
            for row in rows
            if row["route_accuracy"] is not None
        ]

        summary.append({

            "strategy": strategy,

            "attempted": len(rows),

            "successful": len(successful),

            "errors": (
                len(rows) - len(successful)
            ),

            "mean_quality_1_to_5": (
                sum(
                    row["quality_score"]
                    for row in scored
                ) / len(scored)
                if scored else None
            ),

            "total_estimated_cost_usd": sum(costs),

            "avg_latency_ms": (
                sum(latencies) / len(latencies)
                if latencies else None
            ),

            "route_accuracy": (
                sum(route_checks) / len(route_checks)
                if route_checks else None
            )
        })

    # --------------------------------------------------
    # 7. Save summary CSV
    # --------------------------------------------------

    if summary:

        with open(
            SUMMARY_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=summary[0].keys()
            )

            writer.writeheader()
            writer.writerows(summary)

    # --------------------------------------------------
    # 8. Print final report
    # --------------------------------------------------

    print(
        "\n========== EVALUATION SUMMARY =========="
    )

    for row in summary:

        print(
            f"\nStrategy: {row['strategy']}"
        )

        print(
            f"Successful: "
            f"{row['successful']}/{row['attempted']}"
        )

        print(
            f"Errors: {row['errors']}"
        )

        print(
            f"Mean quality: "
            f"{row['mean_quality_1_to_5']}"
        )

        print(
            f"Total cost: "
            f"${row['total_estimated_cost_usd']:.8f}"
        )

        print(
            f"Average latency: "
            f"{row['avg_latency_ms']}"
        )

        print(
            f"Route accuracy: "
            f"{row['route_accuracy']}"
        )

    print(
        f"\nDetailed results: {DETAIL_FILE}"
    )

    print(
        f"Summary results: {SUMMARY_FILE}"
    )


if __name__ == "__main__":
    main()
