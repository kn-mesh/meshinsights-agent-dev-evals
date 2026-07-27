"""Preflight, transform, publish, and verify retained eval bundles."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
from typing import Any

from evaluation import canonical_sha256

from src.benchmarks import PublishedReviewContext
from src.eval_lifecycle import EvalLifecycleService
from src.eval_lifecycle.projection import (
    project_retained_result,
    project_retained_unit,
)
from src.eval_publication.models import (
    PublicationManifest,
    PublicationSeed,
    PublishedArtifact,
)
from src.eval_publication.storage import AzureBlobPublicationStore, PublicationStore


class EvalPublicationError(RuntimeError):
    """A retained eval is not publishable or a publication failed verification."""


@dataclass(frozen=True)
class PreparedPublication:
    """Verified storage-independent publication payloads and identities."""

    retained_eval_id: str
    retained_dir: Path
    project: dict[str, str]
    eval_run_id: str
    run_spec_sha256: str
    selected_example_scope_sha256: str
    benchmark: dict[str, Any]
    agent_version_id: str
    git_commit: str
    counts: dict[str, Any]
    payloads: dict[str, bytes]
    excluded_categories: tuple[str, ...]


class EvalPublicationService:
    """Publish exact retained evals without mutating benchmark truth."""

    def __init__(
        self,
        project_root: Path,
        *,
        eval_root: Path | None = None,
        store: PublicationStore | None = None,
        account_url: str | None = None,
        container: str | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.lifecycle = EvalLifecycleService(
            self.project_root,
            eval_root=eval_root,
        )
        self._store = store
        self._account_url = account_url
        self._container = container

    def dry_run(self, retained_eval_id: str) -> dict[str, Any]:
        """Return a pure preview without allocating a publication event."""
        prepared = self.prepare(retained_eval_id)
        return {
            "operation": "publish",
            "dry_run": True,
            "publication_id": None,
            "publication_allocated": False,
            "project": prepared.project,
            "retained_eval_id": prepared.retained_eval_id,
            "eval_run_id": prepared.eval_run_id,
            "benchmark": prepared.benchmark,
            "destination_parent": self._destination_parent(prepared),
            "artifacts": {
                name: _content_identity(content)
                for name, content in prepared.payloads.items()
            },
            "counts": prepared.counts,
            "excluded_categories": list(prepared.excluded_categories),
        }

    def publish(self, retained_eval_id: str, *, confirmed: bool) -> dict[str, Any]:
        """Create and verify one new immutable publication event."""
        if not confirmed:
            raise EvalPublicationError("Publication requires explicit --yes.")
        prepared = self.prepare(retained_eval_id)
        payload_identities = {
            name: _content_identity(content)
            for name, content in prepared.payloads.items()
        }
        published_at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        seed = PublicationSeed(
            schema_version=1,
            published_at_utc=published_at,
            nonce=secrets.token_hex(32),
            project_key=prepared.project["key"],
            retained_eval_id=prepared.retained_eval_id,
            eval_run_id=prepared.eval_run_id,
            benchmark=prepared.benchmark,
            agent_version_id=prepared.agent_version_id,
            git_commit=prepared.git_commit,
            artifacts=payload_identities,
        )
        publication_id = f"pub_{canonical_sha256(seed.model_dump(mode='json'))[:24]}"
        prefix = f"{self._destination_parent(prepared)}/{publication_id}"
        artifact_contracts = {
            name: PublishedArtifact(
                sha256=str(identity["sha256"]),
                byte_size=int(identity["byte_size"]),
                media_type="application/json",
                blob_name=f"{prefix}/{name}",
            )
            for name, identity in payload_identities.items()
        }
        manifest = PublicationManifest(
            contract="published-eval/v1",
            schema_version=1,
            publication_id=publication_id,
            published_at_utc=published_at,
            project=prepared.project,
            source={
                "retained_eval_id": prepared.retained_eval_id,
                "eval_run_id": prepared.eval_run_id,
            },
            benchmark=prepared.benchmark,
            agent={
                "agent_version_id": prepared.agent_version_id,
                "git_commit": prepared.git_commit,
            },
            run_spec_sha256=prepared.run_spec_sha256,
            selected_example_scope_sha256=prepared.selected_example_scope_sha256,
            counts=prepared.counts,
            artifacts=artifact_contracts,
            publisher_contract_version=1,
            publication_seed=seed,
        )
        store = self._publication_store()
        for name, content in prepared.payloads.items():
            blob_name = artifact_contracts[name].blob_name
            store.create(blob_name, content)
            _verify_content(
                store.read(blob_name),
                identity=payload_identities[name],
                label=blob_name,
            )
        manifest_name = f"{prefix}/publication-manifest.json"
        manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
        store.create(manifest_name, manifest_bytes)
        committed = store.read(manifest_name)
        if committed != manifest_bytes:
            raise EvalPublicationError(
                f"Committed publication manifest verification failed: {manifest_name}"
            )
        self.verify_publication(manifest)
        return {
            "operation": "publish",
            "dry_run": False,
            "published": True,
            "publication_id": publication_id,
            "retained_eval_id": prepared.retained_eval_id,
            "eval_run_id": prepared.eval_run_id,
            "prefix": prefix,
            "manifest_blob": manifest_name,
            "artifacts": {
                name: contract.model_dump(mode="json")
                for name, contract in artifact_contracts.items()
            },
            "verified": True,
        }

    def prepare(self, retained_eval_id: str) -> PreparedPublication:
        """Verify one retained eval and derive its cloud subset without storage."""
        verified = self.lifecycle.verify(retained_eval_id)
        retained_dir = self.project_root / str(verified["path"])
        manifest = _read_object(retained_dir / "manifest.json")
        if manifest.get("schema_version") != 2:
            raise EvalPublicationError(
                "Only occurrence-aware retained eval schema version 2 can be published."
            )
        result = _read_object(retained_dir / "result.json")
        units = _read_object(retained_dir / "units.json")
        evidence = _read_object(retained_dir / "evidence-references.json")
        provenance = _read_object(retained_dir / "agent-provenance.json")
        project = _project_identity(self.project_root)
        run = result.get("run")
        summary = result.get("summary")
        if result.get("schema_version") != 2 or not isinstance(run, dict):
            raise EvalPublicationError("Retained result schema version 2 is required.")
        if not isinstance(summary, dict):
            raise EvalPublicationError("Retained result summary is missing.")
        eval_run_id = str(run.get("eval_run_id") or "")
        if eval_run_id != manifest.get("source_eval_run_id"):
            raise EvalPublicationError("Retained eval occurrence identity is invalid.")
        run_spec_sha256 = _required_digest(run, "run_spec_sha256")
        scope_sha256 = _required_digest(run, "selected_example_scope_sha256")
        _required_text(run, "started_at_utc")
        _required_text(run, "completed_at_utc")
        timing = summary.get("timing")
        if not isinstance(timing, dict) or not _non_negative_number(
            timing.get("evaluation_active_wall_seconds")
        ):
            raise EvalPublicationError("Aggregate active evaluation timing is missing.")
        for key in ("accuracy", "reliability", "scoring_coverage", "usage", "cost"):
            if not isinstance(summary.get(key), dict):
                raise EvalPublicationError(f"Retained result is missing summary.{key}.")
        dimensions = run.get("dimensions")
        if not isinstance(dimensions, dict):
            raise EvalPublicationError("Retained result dimensions are missing.")
        benchmark = _benchmark_identity(dimensions.get("benchmark"))
        _validate_model_and_scoring(run)
        unit_rows = units.get("units")
        if (
            units.get("schema_version") != 2
            or units.get("retained_eval_id") != retained_eval_id
            or not isinstance(unit_rows, list)
            or not unit_rows
        ):
            raise EvalPublicationError("Retained unit aggregate is invalid.")
        incomplete = [
            str(item.get("work_item_id") or item.get("example_id") or "unknown")
            for item in unit_rows
            if not isinstance(item, dict) or item.get("execution_status") != "completed"
        ]
        if incomplete:
            raise EvalPublicationError(
                "Every canonical selected unit must complete before publication: "
                + ", ".join(incomplete[:10])
            )
        _validate_unit_rows(unit_rows)
        git = provenance.get("git")
        if not isinstance(git, dict):
            raise EvalPublicationError("Recorded Git provenance is missing.")
        git_commit = _required_text(git, "git_revision")
        if (
            git.get("tree_state") != "clean"
            or git.get("dirty_overlay_sha256") is not None
            or (retained_dir / "agent.patch").exists()
        ):
            raise EvalPublicationError(
                "Publication requires a clean recorded agent-version surface."
            )
        agent_version_id = _required_text(provenance, "agent_version_id")
        if agent_version_id != manifest.get("agent_version_id"):
            raise EvalPublicationError("Agent-version provenance is inconsistent.")
        agent_dimension = dimensions.get("agent")
        if (
            not isinstance(agent_dimension, dict)
            or agent_dimension.get("agent_version_id") != agent_version_id
            or agent_dimension.get("source_tree_state") != "clean"
        ):
            raise EvalPublicationError(
                "Retained result contradicts clean agent-version provenance."
            )
        if evidence.get("schema_version") != 2:
            raise EvalPublicationError(
                "Evidence-reference schema version 2 is required."
            )
        _validate_evidence_references(evidence, expected_units=unit_rows)
        published_result = _published_result(result)
        published_units = _published_units(
            units,
            eval_run_id=eval_run_id,
        )
        published_provenance = _published_provenance(provenance)
        payloads = {
            "result.json": _json_bytes(published_result),
            "units.json": _json_bytes(published_units),
            "evidence-references.json": _json_bytes(evidence),
            "agent-provenance.json": _json_bytes(published_provenance),
        }
        return PreparedPublication(
            retained_eval_id=retained_eval_id,
            retained_dir=retained_dir,
            project=project,
            eval_run_id=eval_run_id,
            run_spec_sha256=run_spec_sha256,
            selected_example_scope_sha256=scope_sha256,
            benchmark=benchmark,
            agent_version_id=agent_version_id,
            git_commit=git_commit,
            counts=_publication_counts(unit_rows),
            payloads=payloads,
            excluded_categories=(
                "attempt files",
                "invocation logs",
                "retry history",
                "tool traces",
                "intermediate model responses",
                "detailed timing",
                "agent patches",
                "local evidence copies",
            ),
        )

    @staticmethod
    def verify_publication(manifest: PublicationManifest) -> None:
        """Verify the publication ID against its complete event seed."""
        seed = manifest.publication_seed.model_dump(mode="json")
        expected = f"pub_{canonical_sha256(seed)[:24]}"
        if manifest.publication_id != expected:
            raise EvalPublicationError("Publication ID does not match its seed.")
        if (
            manifest.published_at_utc != seed["published_at_utc"]
            or manifest.project["key"] != seed["project_key"]
            or manifest.source["retained_eval_id"] != seed["retained_eval_id"]
            or manifest.source["eval_run_id"] != seed["eval_run_id"]
            or manifest.benchmark != seed["benchmark"]
            or manifest.agent["agent_version_id"] != seed["agent_version_id"]
            or manifest.agent["git_commit"] != seed["git_commit"]
        ):
            raise EvalPublicationError(
                "Publication manifest contradicts its immutable event seed."
            )
        for name, artifact in manifest.artifacts.items():
            identity = seed["artifacts"].get(name)
            if identity != {
                "sha256": artifact.sha256,
                "byte_size": artifact.byte_size,
            }:
                raise EvalPublicationError(
                    f"Publication seed does not bind artifact {name}."
                )

    def _destination_parent(self, prepared: PreparedPublication) -> str:
        benchmark_key = str(prepared.benchmark["key"])
        version = int(prepared.benchmark["version"])
        return (
            f"projects/{prepared.project['key']}/benchmarks/{benchmark_key}/"
            f"v{version}/publications"
        )

    def _publication_store(self) -> PublicationStore:
        if self._store is None:
            self._store = AzureBlobPublicationStore(
                account_url=self._account_url,
                container=self._container,
            )
        return self._store


def _published_result(result: dict[str, Any]) -> dict[str, Any]:
    output = project_retained_result(result)
    output.pop("artifacts", None)
    run = output["run"]
    dimensions = run.get("dimensions", {})
    for key in ("pipeline", "evaluation_profile"):
        if isinstance(dimensions.get(key), dict):
            dimensions[key].pop("path", None)
    return output


def _published_units(
    units: dict[str, Any],
    *,
    eval_run_id: str,
) -> dict[str, Any]:
    output_rows: list[dict[str, Any]] = []
    for item in units["units"]:
        output_rows.append(project_retained_unit(item))
    return {
        "schema_version": 1,
        "retained_eval_id": units["retained_eval_id"],
        "eval_run_id": eval_run_id,
        "units": output_rows,
    }


def _published_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    identity = provenance.get("agent_identity")
    if not isinstance(identity, dict):
        raise EvalPublicationError("Agent manifest identity is missing.")
    source = identity.get("source")
    if not isinstance(source, dict):
        raise EvalPublicationError("Agent source identity is missing.")
    repository_identity = _required_text(source, "repository_id")
    return {
        "schema_version": 1,
        "eval_run_id": provenance["source_run_id"],
        "agent_version_id": provenance["agent_version_id"],
        "agent_version_manifest_sha256": provenance["manifest_sha256"],
        "repository_identity": repository_identity,
        "git_commit": source.get("git_revision"),
        "git_tree": source.get("git_tree"),
        "configuration_hashes": {
            **dict(provenance.get("configuration_hashes") or {}),
            "prompt_assets": canonical_sha256(identity.get("assets", [])),
            "output_schema": canonical_sha256(
                (identity.get("contracts") or {}).get("structured_output", {})
            ),
            "dependency_lock": canonical_sha256(identity.get("dependencies", {})),
            "model_policy": canonical_sha256(identity.get("model_policy", {})),
            "evidence_recipe": canonical_sha256(
                (identity.get("contracts") or {}).get("evidence_recipe", {})
            ),
        },
    }


def _publication_counts(units: list[Any]) -> dict[str, Any]:
    rows = [item for item in units if isinstance(item, dict)]
    examples = {str(item.get("example_id")) for item in rows}
    return {
        "selected_examples": len(examples),
        "selected_units": len(rows),
        "execution_states": dict(
            sorted(Counter(str(item.get("execution_status")) for item in rows).items())
        ),
        "output_contract_states": dict(
            sorted(
                Counter(
                    str(item.get("output_contract_status")) for item in rows
                ).items()
            )
        ),
        "scoring_states": dict(
            sorted(Counter(str(item.get("scoring_status")) for item in rows).items())
        ),
    }


def _validate_unit_rows(units: list[Any]) -> None:
    required_text_fields = (
        "example_id",
        "unit_id",
        "decision_timestamp",
        "source_snapshot_id",
        "work_item_id",
        "execution_status",
        "output_contract_status",
        "scoring_status",
    )
    for index, item in enumerate(units):
        if not isinstance(item, dict):
            raise EvalPublicationError(f"Published unit {index} is not an object.")
        for key in required_text_fields:
            try:
                _required_text(item, key)
            except EvalPublicationError as exc:
                raise EvalPublicationError(
                    f"Published unit {index} is missing required field {key}."
                ) from exc
        if "benchmark_labels" not in item or "agent_output" not in item:
            raise EvalPublicationError(
                f"Published unit {index} is missing labels or agent output."
            )
        if not isinstance(item.get("evaluations"), dict):
            raise EvalPublicationError(
                f"Published unit {index} has invalid grader evaluations."
            )
        context = item.get("published_review_context")
        if not isinstance(context, dict):
            raise EvalPublicationError(
                f"Published unit {index} is missing published reviewer context."
            )
        try:
            PublishedReviewContext.model_validate(context)
        except ValueError as exc:
            raise EvalPublicationError(
                f"Published unit {index} has legacy or invalid reviewer context; "
                "rerun and retain the eval before publication."
            ) from exc


def _validate_evidence_references(
    evidence: dict[str, Any],
    *,
    expected_units: list[Any],
) -> None:
    storage = evidence.get("storage")
    if not isinstance(storage, dict):
        raise EvalPublicationError("Evidence storage identity is missing.")
    for key in ("account_url", "container", "access"):
        _required_text(storage, key)
    for key in (
        "evidence_recipe_id",
        "source_snapshot_contract",
        "benchmark_source_state_sha256",
    ):
        _required_text(evidence, key)
    examples = evidence.get("examples")
    if not isinstance(examples, list) or not examples:
        raise EvalPublicationError("Evidence references are missing.")
    referenced_examples: set[str] = set()
    for index, example in enumerate(examples):
        if not isinstance(example, dict):
            raise EvalPublicationError(f"Evidence reference {index} is not an object.")
        referenced_examples.add(_required_text(example, "example_id"))
        _required_text(example, "source_snapshot_id")
    selected_examples = {
        str(item["example_id"]) for item in expected_units if isinstance(item, dict)
    }
    missing = sorted(selected_examples - referenced_examples)
    if missing:
        raise EvalPublicationError(
            "Evidence references do not cover every selected example: "
            + ", ".join(missing[:10])
        )


def _benchmark_identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvalPublicationError("Published benchmark identity is missing.")
    required = ("project_key", "key", "version_id", "version", "source_state_sha256")
    if any(value.get(key) in {None, ""} for key in required):
        raise EvalPublicationError("Published benchmark identity is incomplete.")
    return {key: deepcopy(value[key]) for key in required}


def _validate_model_and_scoring(run: dict[str, Any]) -> None:
    dimensions = run["dimensions"]
    model = dimensions.get("model")
    scoring = dimensions.get("scoring")
    if not isinstance(model, dict) or any(
        model.get(key) in {None, ""} for key in ("provider", "id", "api")
    ):
        raise EvalPublicationError("Resolved model identity is incomplete.")
    if not isinstance(model.get("pricing"), dict):
        raise EvalPublicationError("Frozen model pricing is missing.")
    if not isinstance(scoring, dict) or not scoring.get("grader_set_sha256"):
        raise EvalPublicationError("Resolved grader identity is missing.")
    if not isinstance(run.get("graders"), list):
        raise EvalPublicationError("Resolved grader configuration is missing.")


def _project_identity(project_root: Path) -> dict[str, str]:
    payload = _read_object(project_root / "workbench.project.json")
    project = payload.get("project")
    if not isinstance(project, dict):
        raise EvalPublicationError("Workbench project identity is missing.")
    key = _required_text(project, "key")
    use_case_key = _required_text(project, "use_case_key")
    return {"key": key, "use_case_key": use_case_key}


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvalPublicationError(f"Required field is missing: {key}.")
    return value


def _required_digest(payload: dict[str, Any], key: str) -> str:
    value = _required_text(payload, key)
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise EvalPublicationError(f"Required SHA-256 field is invalid: {key}.")
    return value


def _non_negative_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    )


def _content_identity(content: bytes) -> dict[str, int | str]:
    return {
        "sha256": hashlib.sha256(content).hexdigest(),
        "byte_size": len(content),
    }


def _verify_content(
    content: bytes,
    *,
    identity: dict[str, int | str],
    label: str,
) -> None:
    if _content_identity(content) != identity:
        raise EvalPublicationError(f"Published artifact verification failed: {label}")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _read_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise EvalPublicationError(
            f"Required artifact is missing: {path.name}"
        ) from error
    if not isinstance(payload, dict):
        raise EvalPublicationError(f"JSON artifact must be an object: {path.name}")
    return payload
