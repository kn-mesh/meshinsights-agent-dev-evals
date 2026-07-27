"""Tests for deterministic identities and persisted attempt round trips."""

from __future__ import annotations

from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_eval_run_identity,
    build_work_item_id,
    canonical_sha256,
    eval_attempt_from_dict,
    eval_attempt_performance_to_dict,
    eval_attempt_to_dict,
    verify_eval_run_identity,
)


def test_canonical_identity_ignores_mapping_order() -> None:
    first = {"model": {"id": "provider:model", "reasoning": "high"}, "runs": 3}
    second = {"runs": 3, "model": {"reasoning": "high", "id": "provider:model"}}

    assert canonical_sha256(first) == canonical_sha256(second)


def test_work_item_identity_is_stable_and_repetition_specific() -> None:
    first = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=1)
    again = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=1)
    second = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=2)

    assert first == again
    assert first != second


def test_eval_occurrences_are_unique_while_binding_the_same_specification() -> None:
    run_spec_sha256 = canonical_sha256({"model": "provider:model"})
    first_id, first_seed = build_eval_run_identity(
        run_spec_sha256=run_spec_sha256,
        created_at_utc="2026-07-23T00:00:00+00:00",
        nonce="first",
    )
    second_id, second_seed = build_eval_run_identity(
        run_spec_sha256=run_spec_sha256,
        created_at_utc="2026-07-23T00:00:00+00:00",
        nonce="second",
    )

    assert first_id != second_id
    assert verify_eval_run_identity(
        first_id,
        occurrence_seed=first_seed,
        run_spec_sha256=run_spec_sha256,
    )
    assert verify_eval_run_identity(
        second_id,
        occurrence_seed=second_seed,
        run_spec_sha256=run_spec_sha256,
    )


def test_eval_attempt_round_trip_preserves_typed_state() -> None:
    attempt = EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.SCORED,
        actual_values={"answer": 3},
        evaluations={
            "answer": FieldEvaluation(
                expected=3,
                actual=3,
                correct=True,
                grader_id="core.exact",
                grader_version=1,
            )
        },
        applicable_fields=("answer",),
        complete_evaluation_correct=True,
        metadata={"run_index": 1},
    )

    assert eval_attempt_from_dict(eval_attempt_to_dict(attempt)) == attempt


def test_eval_and_performance_serialization_have_disjoint_retention_boundaries() -> (
    None
):
    attempt = EvalAttempt(
        execution_status=ExecutionStatus.COMPLETED,
        output_contract_status=OutputContractStatus.VALID,
        scoring_status=ScoringStatus.NO_APPLICABLE_TARGETS,
        actual_values={"answer": 3},
        duration_seconds=12.5,
        stage_durations_seconds={"retrieve": 2.0, "process": 10.5},
        artifacts={
            "agent_output": {"answer": 3},
            "usage": {"input_tokens": 100, "output_tokens": 20},
            "retry_telemetry": {"observed_model_requests": 2},
            "performance": {
                "model_calls": [{"duration_seconds": 9.5, "status": "completed"}]
            },
        },
    )

    durable = eval_attempt_to_dict(attempt)
    performance = eval_attempt_performance_to_dict(attempt)

    assert "duration_seconds" not in durable
    assert "stage_durations_seconds" not in durable
    assert durable["artifacts"] == {
        "agent_output": {"answer": 3},
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }
    assert performance == {
        "schema_version": 1,
        "duration_seconds": 12.5,
        "stage_durations_seconds": {"retrieve": 2.0, "process": 10.5},
        "retry_telemetry": {"observed_model_requests": 2},
        "backend": {"model_calls": [{"duration_seconds": 9.5, "status": "completed"}]},
    }
