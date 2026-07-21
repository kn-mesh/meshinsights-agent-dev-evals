"""Tests for deterministic identities and persisted attempt round trips."""

from __future__ import annotations

from evaluation import (
    EvalAttempt,
    ExecutionStatus,
    FieldEvaluation,
    OutputContractStatus,
    ScoringStatus,
    build_run_identity,
    build_work_item_id,
    canonical_sha256,
    eval_attempt_from_dict,
    eval_attempt_to_dict,
)


def test_canonical_identity_ignores_mapping_order() -> None:
    first = {"model": {"id": "provider:model", "reasoning": "high"}, "runs": 3}
    second = {"runs": 3, "model": {"reasoning": "high", "id": "provider:model"}}

    assert canonical_sha256(first) == canonical_sha256(second)
    assert build_run_identity(first) == build_run_identity(second)


def test_work_item_identity_is_stable_and_repetition_specific() -> None:
    first = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=1)
    again = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=1)
    second = build_work_item_id(run_id="eval_123", item_id="example-a", attempt_index=2)

    assert first == again
    assert first != second


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
