"""Reference-use-case tests for aggregate AI execution telemetry."""

from src.objects.process_object import PulseFailureAnalysisProcessObject


def test_process_object_aggregates_multi_processor_usage_and_retry_observations() -> (
    None
):
    process = PulseFailureAnalysisProcessObject()
    process.set_artifact(
        "orientation_model_usage",
        {
            "requests": 1,
            "input_tokens": 900,
            "output_tokens": 200,
            "cached_input_tokens": 100,
            "reasoning_tokens": 20,
            "tool_calls": 0,
            "output_validation_attempts": 1,
        },
    )
    process.set_artifact(
        "agent_model_usage",
        {
            "requests": 3,
            "input_tokens": 1_600,
            "output_tokens": 150,
            "cached_input_tokens": 0,
            "reasoning_tokens": 50,
            "tool_calls": 1,
            "output_validation_attempts": 0,
        },
    )

    usage = process.get_ai_usage()
    retries = process.get_ai_retry_telemetry()

    assert usage is not None
    assert usage["requests"] == 4
    assert usage["total_tokens"] == 2_850
    assert usage["tool_calls"] == 1
    assert retries["availability"] == "partial"
    assert retries["observed_model_requests"] == 4
    assert retries["observed_transport_attempts"] is None
    assert process.get_execution_telemetry() == {
        "usage": usage,
        "retry_telemetry": retries,
    }


def test_process_object_preserves_performance_without_usage_attachment() -> None:
    process = PulseFailureAnalysisProcessObject()
    process.set_artifact(
        "agent_performance",
        {
            "schema_version": 1,
            "duration_seconds": 3.5,
            "model_calls": [{"duration_seconds": 3.0, "status": "completed"}],
        },
    )

    assert process.get_execution_telemetry() == {
        "usage": None,
        "retry_telemetry": {
            "availability": "unavailable",
            "reason": "No mi.ai usage artifact was produced.",
        },
        "performance": {
            "schema_version": 1,
            "processors": {
                "agent_performance": {
                    "schema_version": 1,
                    "duration_seconds": 3.5,
                    "model_calls": [{"duration_seconds": 3.0, "status": "completed"}],
                }
            },
        },
    }


def test_process_object_reports_transport_attempts_only_when_observed() -> None:
    process = PulseFailureAnalysisProcessObject()
    process.set_artifact(
        "agent_model_usage",
        {
            "requests": 1,
            "input_tokens": 10,
            "output_tokens": 2,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
            "tool_calls": 0,
            "output_validation_attempts": 1,
        },
    )
    process.set_artifact(
        "agent_performance",
        {
            "schema_version": 1,
            "model_calls": [
                {
                    "duration_seconds": 2.0,
                    "status": "completed",
                    "transport_attempts": [
                        {
                            "attempt_number": 1,
                            "terminal_status": "failed",
                            "retry_category": "rate_limit",
                        },
                        {
                            "attempt_number": 2,
                            "terminal_status": "succeeded",
                            "retry_category": None,
                        },
                    ],
                }
            ],
        },
    )

    retries = process.get_ai_retry_telemetry()

    assert retries["availability"] == "available"
    assert retries["observed_transport_attempts"] == 2
    assert retries["observed_transport_retry_categories"] == {"rate_limit": 1}
    assert retries["reason"] is None
