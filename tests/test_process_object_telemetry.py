"""Tests for pipeline-visible aggregate AI execution telemetry."""

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
