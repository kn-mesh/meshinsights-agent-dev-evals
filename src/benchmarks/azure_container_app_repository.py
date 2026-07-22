"""Query hosted Azure PostgreSQL through the deployed Container App."""

from __future__ import annotations

import base64
import json
import re
import subprocess
import zlib
from collections.abc import Callable
from typing import Any

from src.benchmarks.models import BenchmarkVersion, PublishedBenchmarkVersionSummary
from src.benchmarks.postgres_repository import _build_benchmark_version

_PAYLOAD_BEGIN = "__MI_BENCHMARK_PAYLOAD_BEGIN__"
_PAYLOAD_END = "__MI_BENCHMARK_PAYLOAD_END__"
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

_CATALOG_SQL = """
select
  p.project_key,
  b.benchmark_key,
  b.name as benchmark_name,
  bv.id as benchmark_version_id,
  bv.version_number,
  bv.published_at,
  bv.source_state_sha256,
  count(bve.example_id)::integer as example_count
from projects p
join benchmarks b on b.project_id = p.id
join benchmark_versions bv on bv.benchmark_id = b.id
join benchmark_version_examples bve
  on bve.project_id = p.id
 and bve.benchmark_version_id = bv.id
where p.project_key = %(project_key)s
  and bv.published_at is not null
group by
  p.project_key, b.benchmark_key, b.name, bv.id, bv.version_number,
  bv.published_at, bv.source_state_sha256
order by lower(b.name), b.benchmark_key, bv.version_number desc
"""

_VERSION_SQL = """
with selected_version as (
  select
    bv.id,
    bv.project_id,
    bv.version_number,
    bv.published_at,
    bv.source_state_sha256,
    b.benchmark_key,
    b.name as benchmark_name,
    p.project_key,
    ucc.eval_label_fields
  from projects p
  join benchmarks b on b.project_id = p.id
  join benchmark_versions bv on bv.benchmark_id = b.id
  join use_case_configs ucc on ucc.project_id = p.id
  where p.project_key = %(project_key)s
    and b.benchmark_key = %(benchmark_key)s
    and bv.published_at is not null
    and (
      %(version_number)s::integer is null
      or bv.version_number = %(version_number)s
    )
  order by bv.version_number desc
  limit 1
)
select
  sv.project_key,
  sv.benchmark_key,
  sv.benchmark_name,
  sv.id as benchmark_version_id,
  sv.version_number,
  sv.published_at,
  sv.source_state_sha256,
  sv.eval_label_fields,
  bve.example_id,
  bve.unit_id,
  bve.decision_timestamp,
  bve.approved_label_payload,
  bve.label_schema_version_id,
  lsv.schema_key as label_schema_key,
  lsv.version as label_schema_version,
  lsv.schema as label_schema,
  bve.example_metadata,
  bve.source_snapshot_id,
  bve.raw_snapshot_content_sha256,
  bve.raw_source_kind,
  bve.raw_captured_at,
  bve.raw_window_start,
  bve.raw_window_end,
  bve.raw_known_gaps,
  bve.raw_artifacts
from selected_version sv
join benchmark_version_examples bve
  on bve.project_id = sv.project_id
 and bve.benchmark_version_id = sv.id
left join label_schema_versions lsv
  on lsv.project_id = bve.project_id
 and lsv.id = bve.label_schema_version_id
order by bve.example_id
"""


class AzureContainerAppBenchmarkRepository:
    """Run read-only benchmark queries within the deployed Azure application."""

    def __init__(
        self,
        *,
        project_key: str,
        resource_group: str,
        container_app: str,
        api_container: str = "api",
        query_runner: Callable[[str, dict[str, Any]], list[dict[str, Any]]]
        | None = None,
    ) -> None:
        self.project_key = project_key.strip()
        self.resource_group = resource_group.strip()
        self.container_app = container_app.strip()
        self.api_container = api_container.strip()
        if not all(
            (self.project_key, self.resource_group, self.container_app, self.api_container)
        ):
            raise ValueError("Azure deployment and project values must not be empty.")
        self._injected_query_runner = query_runner
        self._hosted_state: dict[str, Any] | None = None

    def list_published_versions(
        self,
    ) -> tuple[PublishedBenchmarkVersionSummary, ...]:
        rows = self._query(_CATALOG_SQL, {"project_key": self.project_key})
        return tuple(
            PublishedBenchmarkVersionSummary.model_validate(
                {
                    **row,
                    "benchmark_version_id": str(row["benchmark_version_id"]),
                }
            )
            for row in rows
        )

    def load_published_version(
        self,
        *,
        benchmark_key: str,
        version_number: int | None = None,
    ) -> BenchmarkVersion:
        normalized_key = benchmark_key.strip()
        if not normalized_key:
            raise ValueError("benchmark_key must not be empty.")
        if version_number is not None and version_number < 1:
            raise ValueError("version_number must be at least 1.")
        rows = self._query(
            _VERSION_SQL,
            {
                "project_key": self.project_key,
                "benchmark_key": normalized_key,
                "version_number": version_number,
            },
        )
        if not rows:
            suffix = "latest" if version_number is None else f"v{version_number}"
            raise ValueError(
                f"Published benchmark {self.project_key}/{normalized_key} ({suffix}) "
                "was not found in the hosted Azure deployment."
            )
        return _build_benchmark_version(
            rows,
        )

    def _query(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._injected_query_runner is not None:
            return self._injected_query_runner(query, parameters)
        return self._run_query(query, parameters)

    def _run_query(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        _ = query
        if self._hosted_state is not None:
            return self._rows_from_hosted_state(self._hosted_state, parameters)
        remote_code = _remote_repository_code()
        encoded_code = base64.b64encode(remote_code.encode("utf-8")).decode("ascii")
        remote_command = (
            ".venv/bin/python -c "
            f"exec(__import__('base64').b64decode('{encoded_code}'))"
        )
        command = [
            "script",
            "-q",
            "/dev/null",
            "az",
            "containerapp",
            "exec",
            "--name",
            self.container_app,
            "--resource-group",
            self.resource_group,
            "--container",
            self.api_container,
            "--command",
            remote_command,
        ]
        last_output = ""
        for _attempt in range(3):
            try:
                result = subprocess.run(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                )
                payload = _decode_remote_payload(result.stdout)
                if len(payload) != 1:
                    raise ValueError("Hosted benchmark state payload was invalid.")
                self._hosted_state = payload[0]
                return self._rows_from_hosted_state(self._hosted_state, parameters)
            except FileNotFoundError as error:
                raise ValueError(
                    "Azure CLI and the system 'script' command are required for "
                    "hosted benchmark retrieval."
                ) from error
            except subprocess.CalledProcessError as error:
                last_output = error.stderr.strip() or error.stdout.strip()
            except ValueError as error:
                last_output = str(error)
        detail = _terminal_error_summary(last_output)
        raise ValueError("Could not query hosted benchmarks: " + detail)

    def _rows_from_hosted_state(
        self,
        state: dict[str, Any],
        parameters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if state.get("project_key") != self.project_key:
            raise ValueError("Hosted Azure deployment returned the wrong project.")
        versions = state.get("versions")
        if not isinstance(versions, list):
            raise ValueError("Hosted benchmark state payload was invalid.")
        benchmark_key = parameters.get("benchmark_key")
        if benchmark_key is None:
            return [
                {
                    "project_key": self.project_key,
                    "benchmark_key": version["benchmark_key"],
                    "benchmark_name": version["benchmark_name"],
                    "benchmark_version_id": version["id"],
                    "version_number": version["version_number"],
                    "published_at": version["published_at"],
                    "source_state_sha256": version.get("source_state_sha256"),
                    "example_count": len(version["examples"]),
                }
                for version in versions
            ]
        version_number = parameters.get("version_number")
        selected = [
            version
            for version in versions
            if version["benchmark_key"] == benchmark_key
            and (
                version_number is None
                or int(version["version_number"]) == version_number
            )
        ]
        if version_number is None and selected:
            selected = [max(selected, key=lambda item: int(item["version_number"]))]
        rows: list[dict[str, Any]] = []
        for version in selected:
            schemas = {
                item["schema_version_id"]: item
                for item in version.get("label_schemas", [])
            }
            for example in version["examples"]:
                schema = schemas.get(str(example.get("label_schema_version_id")))
                if schema is None:
                    raise ValueError(
                        "Hosted benchmark example referenced a missing label schema."
                    )
                rows.append(
                    {
                        "project_key": self.project_key,
                        "benchmark_key": version["benchmark_key"],
                        "benchmark_name": version["benchmark_name"],
                        "benchmark_version_id": version["id"],
                        "version_number": version["version_number"],
                        "published_at": version["published_at"],
                        "source_state_sha256": version.get("source_state_sha256"),
                        "published_contract_schema_version": version.get(
                            "published_contract_schema_version"
                        ),
                        "eval_label_fields": version.get(
                            "eval_label_field_hints", []
                        ),
                        **example,
                        "label_schema_key": schema["schema_key"],
                        "label_schema_version": schema["version"],
                        "label_schema": schema["schema"],
                        "label_schema_content_sha256": schema.get("content_sha256"),
                    }
                )
        return rows


def _remote_repository_code() -> str:
    """Use deployed repository functions to keep the exec command compact."""
    return f"""\
import base64
import json
import zlib
from label_benchmark.db import connect as C
from label_benchmark.repositories import load_config as G, load_project as P, load_versions as V
with C() as c:
 c.execute("set transaction read only");p=P(c);g=G(c,p["id"]);v=V(c,p["id"],eval_label_fields=g["eval_label_fields"])
rows=[{{"project_key":p["project_key"],"versions":v}}]
payload=json.dumps(rows,default=str).encode()
encoded = base64.b64encode(zlib.compress(payload)).decode("ascii")
print("{_PAYLOAD_BEGIN}" + encoded + "{_PAYLOAD_END}")
"""


def _decode_remote_payload(output: str) -> list[dict[str, Any]]:
    cleaned = _ANSI_ESCAPE.sub("", output).replace("\r", "")
    start = cleaned.find(_PAYLOAD_BEGIN)
    end = cleaned.find(_PAYLOAD_END, start + len(_PAYLOAD_BEGIN))
    if start < 0 or end < 0:
        raise ValueError(
            "Hosted benchmark query did not return a payload. Verify Azure CLI "
            "access to the deployed Container App."
        )
    encoded = "".join(
        cleaned[start + len(_PAYLOAD_BEGIN) : end].split()
    )
    try:
        parsed = json.loads(zlib.decompress(base64.b64decode(encoded)))
    except (ValueError, zlib.error, json.JSONDecodeError) as error:
        raise ValueError("Hosted benchmark payload could not be decoded.") from error
    if not isinstance(parsed, list) or not all(isinstance(row, dict) for row in parsed):
        raise ValueError("Hosted benchmark payload must be a list of rows.")
    return parsed


def _terminal_error_summary(output: str) -> str:
    cleaned = _ANSI_ESCAPE.sub("", output).replace("\r", " ")
    if "Handshake status 404" in cleaned:
        return "Azure Container App exec endpoint was temporarily unavailable."
    return "Azure Container App query failed."
