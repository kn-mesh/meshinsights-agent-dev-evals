"""Fixed Agent Workbench project-layout conventions."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


USE_CASE_ROOT = "use_case"
USE_CASE_DOCS = "use_case/docs"
USE_CASE_PIPELINE_CONFIGS = "use_case/pipeline_configs"
USE_CASE_EVALUATION_CONFIGS = "use_case/evaluation_configs"
USE_CASE_AGENT_VERSION_CONFIGS = "use_case/agent_version_configs"
USE_CASE_ACTIONS = "use_case/actions"
USE_CASE_EVIDENCE = "use_case/evidence"
USE_CASE_HYDRATORS = "use_case/hydrators"
USE_CASE_OBJECTS = "use_case/objects"
USE_CASE_PROCESSORS = "use_case/processors"
USE_CASE_RETRIEVERS = "use_case/retrievers"
USE_CASE_GRADERS = "use_case/graders"
USE_CASE_EXPLORER = "use_case/explorer"
USE_CASE_TESTS = "use_case/tests"

USE_CASE_DIRECTORIES = (
    USE_CASE_DOCS,
    USE_CASE_PIPELINE_CONFIGS,
    USE_CASE_EVALUATION_CONFIGS,
    USE_CASE_AGENT_VERSION_CONFIGS,
    USE_CASE_ACTIONS,
    USE_CASE_EVIDENCE,
    USE_CASE_HYDRATORS,
    USE_CASE_OBJECTS,
    USE_CASE_PROCESSORS,
    USE_CASE_RETRIEVERS,
    USE_CASE_GRADERS,
    USE_CASE_EXPLORER,
    USE_CASE_TESTS,
)

USE_CASE_PYTHON_DIRECTORIES = (
    USE_CASE_ROOT,
    USE_CASE_ACTIONS,
    USE_CASE_EVIDENCE,
    USE_CASE_HYDRATORS,
    USE_CASE_OBJECTS,
    USE_CASE_PROCESSORS,
    USE_CASE_RETRIEVERS,
    USE_CASE_GRADERS,
    USE_CASE_TESTS,
)


def project_path(project_root: Path, relative: str) -> Path:
    """Resolve one fixed convention inside a project root."""
    normalized = PurePosixPath(relative)
    if (
        not relative
        or normalized.is_absolute()
        or ".." in normalized.parts
        or normalized.as_posix() != relative
    ):
        raise ValueError(f"Project path must be normalized and relative: {relative!r}")
    root = project_root.resolve()
    target = (root / relative).resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError(f"Project path escapes the project root: {relative!r}")
    return target
