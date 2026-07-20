"""Tests for structured pipeline-stage failure diagnostics."""

from __future__ import annotations

from mi.core.pipeline import _record_stage_exception
from mi.core.pipeline_receipt import StageReceipt


def test_stage_error_details_preserve_exception_chain_and_request_identity() -> None:
    class ProviderError(Exception):
        status_code = 503
        request_id = "request-123"

    provider_error = ProviderError("temporarily unavailable")
    normalized_error = ValueError("workflow failed")
    normalized_error.__cause__ = provider_error
    receipt = StageReceipt("process", False, 0.0)

    _record_stage_exception(receipt, normalized_error)

    assert receipt.metadata["error_details"] == {
        "exception_chain": [
            {"exception_type": "ValueError", "message": "workflow failed"},
            {
                "exception_type": "ProviderError",
                "message": "temporarily unavailable",
                "status_code": 503,
                "request_id": "request-123",
            },
        ]
    }
