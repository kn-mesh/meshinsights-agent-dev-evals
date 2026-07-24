"""One-off live verification of provider usage normalization and cost estimates.

This script intentionally lives outside pytest discovery. It makes billable API
calls and should only be run explicitly:

    uv run python -m scripts.verify_live_provider_costs
"""

from __future__ import annotations

import argparse
import json
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict

from mi.ai.backends.base import WorkflowRequest
from mi.ai.backends.pydantic_ai_backend import PydanticAIBackend
from mi.ai.message import UserMessage
from mi.ai.model_config import ModelRef, ReasoningEffort, ReasoningSpec
from mi.core import bootstrap_environment

from model_catalog import resolve_model_definition
from src.evals.eval_orchestration import _estimate_cost_from_usage


DEFAULT_MODELS = (
    "azure:gpt-5.6-luna",
    "azure:claude-haiku-4-5",
    "google:gemini-3.5-flash-lite",
)


class LiveCheckOutput(BaseModel):
    """Minimal structured response used to keep live verification inexpensive."""

    model_config = ConfigDict(extra="forbid")

    ok: Literal[True]


def _verify_model(model_id: str) -> dict[str, object]:
    definition = resolve_model_definition(model_id)
    if definition.pricing is None:
        raise RuntimeError(f"No frozen pricing is configured for {model_id}.")
    model = ModelRef.parse(model_id)
    exercise_reasoning = (
        model.provider == "google"
        or model.provider == "azure"
        and not model.model.startswith("claude")
    )
    reasoning_effort = (
        ReasoningEffort.LOW if exercise_reasoning else ReasoningEffort.MINIMAL
    )
    result = PydanticAIBackend().run_workflow(
        WorkflowRequest(
            model=model,
            system_prompt="Return the requested structured value only.",
            user_message=UserMessage().add_text(
                "Check whether 17 multiplied by 19 equals 323, then set ok to true."
            ),
            output_schema=LiveCheckOutput,
            reasoning_spec=ReasoningSpec(
                efforts={
                    ReasoningEffort.MINIMAL: False,
                    ReasoningEffort.LOW: ReasoningEffort.LOW,
                }
            ),
            reasoning_effort=reasoning_effort,
            transport_retries=1,
            output_retries=0,
            timeout=60,
            backend_options={"model_api": definition.api},
        )
    )
    if result.output != LiveCheckOutput(ok=True):
        raise AssertionError(f"{model_id} returned an unexpected structured value.")
    if not result.usage.model_requests:
        raise AssertionError(f"{model_id} returned no request-level usage.")

    usage = {
        "requests": result.usage.requests,
        "input_tokens": result.usage.input_tokens,
        "output_tokens": result.usage.output_tokens,
        "cached_input_tokens": result.usage.cached_input_tokens,
        "cache_write_tokens": result.usage.cache_write_tokens,
        "reasoning_tokens": result.usage.reasoning_tokens,
        "model_requests": [
            request.to_dict() for request in result.usage.model_requests
        ],
    }
    for request in usage["model_requests"]:
        reported = request["reported"]
        billable = request["billable"]
        input_children = (
            billable["input_uncached_tokens"]
            + billable["input_cache_read_tokens"]
            + billable["input_cache_write_tokens"]
        )
        output_children = (
            billable["output_visible_tokens"] + billable["output_reasoning_tokens"]
        )
        if input_children != reported["input_tokens"]:
            raise AssertionError(
                f"{model_id} input buckets do not reconcile: "
                f"{input_children} != {reported['input_tokens']}."
            )
        if output_children != reported["output_tokens"]:
            raise AssertionError(
                f"{model_id} output buckets do not reconcile: "
                f"{output_children} != {reported['output_tokens']}."
            )

    cost = _estimate_cost_from_usage(usage, definition.pricing)
    estimated = cost.get("estimated")
    if not isinstance(estimated, dict):
        raise AssertionError(f"{model_id} did not produce an estimate.")
    line_item_total = sum(
        line["amount"]
        for request_cost in estimated["requests"]
        for line in request_cost["line_items"]
    )
    if not math.isclose(
        line_item_total,
        estimated["amount"],
        rel_tol=1e-12,
        abs_tol=1e-15,
    ):
        raise AssertionError(f"{model_id} line items do not sum to the estimate.")
    if estimated.get("input_pricing_policy") != "assume_uncached":
        raise AssertionError(f"{model_id} did not use the uncached-input policy.")
    for request_usage, request_cost in zip(
        usage["model_requests"], estimated["requests"], strict=True
    ):
        input_lines = [
            line for line in request_cost["line_items"] if line["meter"] == "input_tokens"
        ]
        if len(input_lines) != 1:
            raise AssertionError(
                f"{model_id} did not produce exactly one full-rate input line item."
            )
        input_line = input_lines[0]
        if input_line["quantity"] != request_usage["reported"]["input_tokens"]:
            raise AssertionError(
                f"{model_id} did not price every reported input token."
            )
        if input_line["rate_per_million"] != (
            definition.pricing.input_per_million_tokens
        ):
            raise AssertionError(f"{model_id} did not use the ordinary input rate.")
        if any("cache" in line["meter"] for line in request_cost["line_items"]):
            raise AssertionError(f"{model_id} included a cache meter in estimated cost.")
    if cost["status"] != "estimated_complete":
        raise AssertionError(
            f"{model_id} live call has incomplete pricing coverage: "
            f"{cost['unpriced_usage']}"
        )
    return {
        "model": model_id,
        "api": definition.api,
        "usage": usage,
        "cost": cost,
        "verification": {
            "structured_output": "passed",
            "input_bucket_reconciliation": "passed",
            "output_bucket_reconciliation": "passed",
            "line_item_recalculation": "passed",
            "uncached_input_pricing": "passed",
            "reasoning_requested": exercise_reasoning,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Make explicit billable calls to verify provider cost telemetry."
    )
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Override the default provider:model set; repeat for multiple models.",
    )
    args = parser.parse_args()
    bootstrap_environment()
    reports = [_verify_model(model) for model in (args.models or DEFAULT_MODELS)]
    print(json.dumps({"schema_version": 1, "reports": reports}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
