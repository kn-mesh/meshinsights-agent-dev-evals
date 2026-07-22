"""Tests for disposable run-scoped evaluation review storage."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart

from evaluation import LocalReviewStore, ReviewStoreError
import evaluation.review as review_module
from mi.ai.backends.pydantic_ai_backend import PydanticAIBackend
from mi.ai.message import UserMessage
from mi.ai.review import serialize_messages


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "eval_review"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(
        json.dumps({"run_id": "eval_review"}), encoding="utf-8"
    )
    (run_dir / "result.json").write_text("{}", encoding="utf-8")
    return run_dir


def test_review_store_deduplicates_within_run_and_purges_only_review(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review", inline_text_bytes=32)
    store.initialize(run_spec_sha256="a" * 64)
    image = base64.b64encode(b"same-image").decode("ascii")
    long_prompt = "same long prompt" * 4

    store.commit_execution(
        {
            "run_id": "eval_review",
            "work_item_id": "work_a",
            "execution_id": "work_a.1",
            "capture_status": "complete",
            "model_interactions": {
                "prompt_a": long_prompt,
                "prompt_b": long_prompt,
                "images": [
                    {
                        "kind": "image",
                        "base64_data": image,
                        "media_type": "image/png",
                    },
                    {
                        "kind": "image",
                        "base64_data": image,
                        "media_type": "image/png",
                    },
                ],
                "authorization": "must-not-persist",
                "authorization_header": "Bearer must-not-persist",
                "database_url": "postgresql://user:password@example.test/db",
                "token": "must-not-persist",
                "source_url": "https://example.test/blob?sig=secret",
                "signed_reference": "https://example.test/blob?sig=secret",
                "provider_value": "Bearer must-not-persist",
                "error_message": (
                    "upstream returned Authorization: Bearer embedded-must-not-persist"
                ),
            },
        }
    )

    verified = store.verify()
    assert verified["unique_local_objects"] == 2
    assert verified["local_references"] == 4
    serialized = store.read_execution("work_a.1", resolve_text=True)
    interactions = serialized["model_interactions"]
    assert interactions["prompt_a"]["content"] == long_prompt
    assert interactions["authorization"]["redacted"] is True
    assert interactions["authorization_header"]["redacted"] is True
    assert interactions["database_url"]["redacted"] is True
    assert interactions["token"]["redacted"] is True
    assert interactions["source_url"] == "https://example.test/blob"
    assert interactions["signed_reference"] == "https://example.test/blob"
    assert interactions["provider_value"]["redacted"] is True
    assert interactions["error_message"]["redacted"] is True
    persisted = next(store.executions_dir.glob("*/*.json")).read_text(encoding="utf-8")
    assert "must-not-persist" not in persisted
    assert "postgresql://user:password" not in persisted
    assert "embedded-must-not-persist" not in persisted

    diagnosis, _ = store.write_diagnosis({"hypothesis": "prompt is ambiguous"})
    preview = store.purge(dry_run=True)
    assert preview["file_count"] > 0
    assert store.purge(dry_run=False, confirmed=True)["purged"] is True
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "result.json").exists()
    assert diagnosis.exists()
    assert json.loads(store.capture_path.read_text())["status"] == "purged"

    # A later failed-work generation may capture a new ephemeral review bundle.
    store.initialize(run_spec_sha256="a" * 64)
    assert json.loads(store.capture_path.read_text())["status"] == "in_progress"


def test_review_store_accepts_actual_pydantic_ai_urlsafe_binary_serialization(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    content = bytes(range(256))
    message = UserMessage().add_image_bytes(content)
    serialized = serialize_messages(
        [
            ModelRequest(
                parts=[
                    SystemPromptPart(content="system"),
                    UserPromptPart(
                        content=PydanticAIBackend()._build_user_content(message)
                    ),
                ]
            )
        ]
    )
    binary = serialized[0]["parts"][1]["content"][0]
    assert binary["kind"] == "binary"
    assert "-" in binary["data"] or "_" in binary["data"]

    store.commit_execution(
        {
            "run_id": "eval_review",
            "work_item_id": "work_a",
            "execution_id": "work_a.1",
            "capture_status": "complete",
            "model_interactions": {"messages": serialized},
        }
    )
    store.finalize(expected_execution_ids=["work_a.1"])

    assert next(store.objects_dir.glob("*/*")).read_bytes() == content
    assert store.verify()["status"] == "complete"


def test_review_commit_rolls_back_objects_when_manifest_publish_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review", inline_text_bytes=0)
    store.initialize(run_spec_sha256="a" * 64)
    original = LocalReviewStore._write_bytes_create

    def fail_manifest(path: Path, content: bytes) -> None:
        if store.executions_dir in path.parents:
            raise OSError("simulated manifest failure")
        original(path, content)

    monkeypatch.setattr(
        LocalReviewStore, "_write_bytes_create", staticmethod(fail_manifest)
    )
    with pytest.raises(OSError, match="simulated manifest failure"):
        store.commit_execution(
            {
                "run_id": "eval_review",
                "work_item_id": "work_a",
                "execution_id": "work_a.1",
                "capture_status": "complete",
                "model_interactions": {"prompt": "externalized"},
            }
        )

    assert not tuple(store.executions_dir.glob("*/*.json"))
    assert not tuple(store.objects_dir.glob("*/*"))


def test_review_failure_finalizes_truthfully_and_records_bounded_reason(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    error = ReviewStoreError("Invalid base64 review artifact.")
    store.record_failure(execution_id="work_a.1", work_item_id="work_a", error=error)
    capture = store.finalize(expected_execution_ids=["work_a.1"])

    assert capture["status"] == "failed"
    assert capture["expected_execution_count"] == 1
    assert capture["captured_execution_count"] == 0
    assert capture["missing_execution_ids"] == ["work_a.1"]
    assert capture["capture_failures"][0]["error_type"] == "ReviewStoreError"


def test_review_finalize_reports_partial_when_only_some_executions_commit(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    store.commit_execution(
        {
            "run_id": "eval_review",
            "work_item_id": "work_a",
            "execution_id": "work_a.1",
            "capture_status": "complete",
        }
    )

    capture = store.finalize(expected_execution_ids=["work_a.1", "work_b.1"])

    assert capture["status"] == "partial"
    assert capture["captured_execution_count"] == 1
    assert capture["missing_execution_ids"] == ["work_b.1"]


def test_review_store_rejects_malformed_binary_without_leaving_objects(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    with pytest.raises(ReviewStoreError, match="Invalid base64"):
        store.commit_execution(
            {
                "run_id": "eval_review",
                "work_item_id": "work_a",
                "execution_id": "work_a.1",
                "capture_status": "complete",
                "model_interactions": {
                    "messages": [
                        {
                            "kind": "binary",
                            "data": "not***base64",
                            "media_type": "image/png",
                        }
                    ]
                },
            }
        )
    assert not tuple(store.objects_dir.glob("*/*"))
    assert not tuple(store.executions_dir.glob("*/*.json"))


def test_review_store_rejects_unconfirmed_mutating_purge(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)

    try:
        store.purge(dry_run=False)
    except RuntimeError as error:
        assert "explicit confirmation" in str(error)
    else:  # pragma: no cover - safety assertion
        raise AssertionError("Purge unexpectedly ran without confirmation.")


def test_review_store_rejects_symlinked_review_directory(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (run_dir / "review").symlink_to(outside, target_is_directory=True)
    store = LocalReviewStore(run_dir, run_id="eval_review")

    try:
        store.initialize(run_spec_sha256="a" * 64)
    except RuntimeError as error:
        assert "escapes" in str(error) or "symlink" in str(error)
    else:  # pragma: no cover - safety assertion
        raise AssertionError("Symlinked review directory was accepted.")


def test_review_store_restores_bundle_when_purge_deletion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    retained = store.review_dir / "retained.txt"
    retained.write_text("review evidence", encoding="utf-8")

    with monkeypatch.context() as context:
        context.setattr(
            review_module.shutil,
            "rmtree",
            lambda _path: (_ for _ in ()).throw(OSError("simulated interruption")),
        )
        with pytest.raises(OSError, match="simulated interruption"):
            store.purge(dry_run=False, confirmed=True)

    assert retained.read_text(encoding="utf-8") == "review evidence"
    assert not store.purge_staging_dir.exists()
    assert store.purge(dry_run=True)["file_count"] >= 2
    assert store.purge(dry_run=False, confirmed=True)["purged"] is True


def test_review_store_recovers_a_bundle_staged_by_an_interrupted_process(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    retained = store.review_dir / "retained.txt"
    retained.write_text("review evidence", encoding="utf-8")
    os.replace(store.review_dir, store.purge_staging_dir)

    preview = store.purge(dry_run=True)

    assert preview["file_count"] >= 2
    assert retained.read_text(encoding="utf-8") == "review evidence"
    assert not store.purge_staging_dir.exists()


def test_review_store_rejects_tampered_manifest_and_object(tmp_path: Path) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review", inline_text_bytes=0)
    store.initialize(run_spec_sha256="a" * 64)
    store.commit_execution(
        {
            "run_id": "eval_review",
            "work_item_id": "work_a",
            "execution_id": "work_a.1",
            "capture_status": "complete",
            "model_interactions": {"prompt": "long prompt stored externally"},
        }
    )

    manifest_path = next(store.executions_dir.glob("*/*.json"))
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)
    manifest["capture_status"] = "partial"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ReviewStoreError, match="manifest hash"):
        store.verify()

    manifest_path.write_bytes(original_manifest)
    object_path = next(store.objects_dir.glob("*/*"))
    object_path.write_bytes(b"tampered review evidence")
    with pytest.raises(ReviewStoreError, match="object digest mismatch"):
        store.verify()


def test_review_verify_rejects_orphans_and_capture_count_mismatch(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")
    store.initialize(run_spec_sha256="a" * 64)
    store.commit_execution(
        {
            "run_id": "eval_review",
            "work_item_id": "work_a",
            "execution_id": "work_a.1",
            "capture_status": "complete",
        }
    )
    store.finalize(expected_execution_ids=["work_a.1"])

    orphan_content = b"orphan"
    orphan_digest = hashlib.sha256(orphan_content).hexdigest()
    orphan = store.objects_dir / orphan_digest[:2] / orphan_digest
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(orphan_content)
    with pytest.raises(ReviewStoreError, match="Orphaned review objects"):
        store.verify()

    orphan.unlink()
    capture = json.loads(store.capture_path.read_text())
    capture["object_count"] = 99
    store.capture_path.write_text(json.dumps(capture), encoding="utf-8")
    with pytest.raises(ReviewStoreError, match="object_count"):
        store.verify()


def test_diagnosis_markdown_does_not_persist_embedded_credentials(
    tmp_path: Path,
) -> None:
    run_dir = _run_dir(tmp_path)
    store = LocalReviewStore(run_dir, run_id="eval_review")

    _, markdown_path = store.write_diagnosis(
        {"hypothesis": "provider authentication failed"},
        markdown="Observed Authorization: Bearer must-not-persist in the trace.",
    )

    assert markdown_path is not None
    persisted = markdown_path.read_text(encoding="utf-8")
    assert "must-not-persist" not in persisted
    assert "REDACTED" in persisted
