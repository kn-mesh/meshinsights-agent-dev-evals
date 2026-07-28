"""Dependency-injected, use-case-neutral FastAPI explorer application."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


class ExplorerBackend(Protocol):
    def list_runs(self) -> dict[str, Any]: ...
    def list_campaigns(self) -> dict[str, Any]: ...
    def get_campaign(self, campaign_id: str) -> dict[str, Any]: ...
    def get_run(self, run_id: str) -> dict[str, Any]: ...
    def get_performance(self, run_id: str) -> dict[str, Any]: ...
    def list_attempts(
        self,
        run_id: str,
        *,
        state: str,
        search: str,
        field: str | None,
        slice_key: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]: ...
    def get_attempt(self, run_id: str, execution_id: str) -> dict[str, Any]: ...
    def get_evidence(self, run_id: str, example_id: str) -> dict[str, Any]: ...


def create_app(*, backend: ExplorerBackend, static_dir: Path | None = None) -> FastAPI:
    """Create the reusable app without importing a project use case."""
    app = FastAPI(title="Agent Workbench Eval Explorer", version="1")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runs")
    def list_runs() -> dict[str, Any]:
        return _call(backend.list_runs)

    @app.get("/api/campaigns")
    def list_campaigns() -> dict[str, Any]:
        return _call(backend.list_campaigns)

    @app.get("/api/campaigns/{campaign_id}")
    def get_campaign(campaign_id: str) -> dict[str, Any]:
        return _call(backend.get_campaign, campaign_id)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        return _call(backend.get_run, run_id)

    @app.get("/api/runs/{run_id}/performance")
    def get_performance(run_id: str) -> dict[str, Any]:
        return _call(backend.get_performance, run_id)

    @app.get("/api/runs/{run_id}/attempts")
    def list_attempts(
        run_id: str,
        state: str = "all",
        search: str = "",
        field: str | None = None,
        slice_key: str | None = Query(default=None, alias="slice"),
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        return _call(
            backend.list_attempts,
            run_id,
            state=state,
            search=search,
            field=field,
            slice_key=slice_key,
            offset=offset,
            limit=limit,
        )

    @app.get("/api/runs/{run_id}/attempts/{execution_id}")
    def get_attempt(run_id: str, execution_id: str) -> dict[str, Any]:
        return _call(backend.get_attempt, run_id, execution_id)

    @app.get("/api/runs/{run_id}/examples/{example_id}/evidence")
    def get_evidence(run_id: str, example_id: str) -> dict[str, Any]:
        return _call(backend.get_evidence, run_id, example_id)

    resolved_static = static_dir.resolve() if static_dir is not None else None
    if resolved_static is not None and (resolved_static / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=resolved_static / "assets"),
            name="assets",
        )

    if resolved_static is not None and (resolved_static / "index.html").is_file():

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(status_code=404, detail="API route not found.")
            return FileResponse(resolved_static / "index.html")

    return app


def _call(function: Any, *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
