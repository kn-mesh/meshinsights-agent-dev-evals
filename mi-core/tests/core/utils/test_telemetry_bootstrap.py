"""Tests for telemetry bootstrap behaviour.

Verifies that ``bootstrap_telemetry()`` correctly detects Logfire / OTel SDK,
respects the ``PipelineConfig.bootstrap_otel`` flag, and behaves correctly
in the orchestrator subprocess path.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import builtins

import mi.core.utils.telemetry as telemetry_mod
from mi.core.utils.telemetry import bootstrap_telemetry

# Capture the real __import__ before any patching
_real_import = builtins.__import__


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_bootstrap_state():
    """Reset module-level ``_bootstrapped`` flag before each test."""
    telemetry_mod._bootstrapped = False
    yield
    telemetry_mod._bootstrapped = False


# ---------------------------------------------------------------------------
# NOTE: bootstrap_telemetry — idempotency
# ---------------------------------------------------------------------------


class TestBootstrapIdempotency:
    """bootstrap_telemetry() must only execute its detection logic once."""

    def test_second_call_is_noop(self):
        mock_logfire = MagicMock()
        with patch.dict(sys.modules, {"logfire": mock_logfire}):
            bootstrap_telemetry()
            bootstrap_telemetry()

        mock_logfire.configure.assert_called_once()

    def test_bootstrapped_flag_set_after_first_call(self):
        assert telemetry_mod._bootstrapped is False
        with patch.dict(sys.modules, {"logfire": MagicMock()}):
            bootstrap_telemetry()
        assert telemetry_mod._bootstrapped is True

    def test_bootstrapped_flag_prevents_reentry_even_after_failure(self):
        """If the first call fails, subsequent calls still skip."""
        bad_logfire = MagicMock()
        bad_logfire.configure.side_effect = RuntimeError("boom")

        with (
            patch.dict(sys.modules, {"logfire": bad_logfire}),
            patch.dict("os.environ", {}, clear=True),
        ):
            bootstrap_telemetry()

        assert telemetry_mod._bootstrapped is True

        # Second call with a working logfire — should NOT be invoked
        good_logfire = MagicMock()
        with patch.dict(sys.modules, {"logfire": good_logfire}):
            bootstrap_telemetry()

        good_logfire.configure.assert_not_called()


# ---------------------------------------------------------------------------
# NOTE: bootstrap_telemetry — Logfire detection (path 1)
# ---------------------------------------------------------------------------


class TestBootstrapLogfirePath:
    """When logfire is importable, bootstrap_telemetry() should call
    logfire.configure() with safe defaults."""

    def test_calls_logfire_configure_with_safe_defaults(self):
        mock_logfire = MagicMock()
        with patch.dict(sys.modules, {"logfire": mock_logfire}):
            bootstrap_telemetry()

        mock_logfire.configure.assert_called_once_with(
            send_to_logfire="if-token-present",
            console=False,
        )

    def test_returns_after_logfire_success(self):
        """When Logfire succeeds, the OTel SDK fallback must NOT run."""
        mock_logfire = MagicMock()

        with (
            patch.dict(sys.modules, {"logfire": mock_logfire}),
            patch("mi.core.utils.telemetry.trace") as mock_trace,
        ):
            bootstrap_telemetry()

        # trace.set_tracer_provider is only called in path 2 (OTel fallback)
        mock_trace.set_tracer_provider.assert_not_called()

    def test_falls_through_when_logfire_configure_raises(self):
        """If logfire.configure() raises, fall through to OTel SDK path."""
        bad_logfire = MagicMock()
        bad_logfire.configure.side_effect = RuntimeError("token issue")

        with (
            patch.dict(sys.modules, {"logfire": bad_logfire}),
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
                clear=False,
            ),
            patch("mi.core.utils.telemetry.trace") as mock_trace,
        ):
            bootstrap_telemetry()

            # set_tracer_provider confirms path 2 executed
            mock_trace.set_tracer_provider.assert_called_once()


# ---------------------------------------------------------------------------
# NOTE: bootstrap_telemetry — OTel SDK fallback (path 2)
# ---------------------------------------------------------------------------


class TestBootstrapOtelFallback:
    """When logfire is NOT available, bootstrap_telemetry() should fall back
    to configuring a global TracerProvider via the OTel SDK."""

    @staticmethod
    def _logfire_import_blocker(name: str, *args: Any, **kwargs: Any) -> Any:
        """An __import__ wrapper that blocks ``import logfire``."""
        if name == "logfire":
            raise ImportError("blocked by test")
        return _real_import(name, *args, **kwargs)

    def test_configures_global_provider_when_endpoint_set(self):
        """With OTEL_EXPORTER_OTLP_ENDPOINT set and SDK available, a global
        TracerProvider should be configured."""
        with (
            patch("builtins.__import__", side_effect=self._logfire_import_blocker),
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
                clear=False,
            ),
            patch("mi.core.utils.telemetry.trace") as mock_trace,
        ):
            bootstrap_telemetry()

            mock_trace.set_tracer_provider.assert_called_once()

    def test_noop_when_no_endpoint(self):
        """Without OTEL_EXPORTER_OTLP_ENDPOINT, path 2 is a no-op."""
        env = {
            k: v
            for k, v in __import__("os").environ.items()
            if k != "OTEL_EXPORTER_OTLP_ENDPOINT"
        }

        with (
            patch("builtins.__import__", side_effect=self._logfire_import_blocker),
            patch.dict("os.environ", env, clear=True),
            patch("mi.core.utils.telemetry.trace") as mock_trace,
        ):
            bootstrap_telemetry()

            mock_trace.set_tracer_provider.assert_not_called()


# ---------------------------------------------------------------------------
# NOTE: bootstrap_telemetry — full no-op (path 3)
# ---------------------------------------------------------------------------


class TestBootstrapNoop:
    """When neither Logfire nor OTel SDK + endpoint are available,
    bootstrap_telemetry() should silently no-op."""

    @staticmethod
    def _block_logfire(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "logfire":
            raise ImportError("blocked by test")
        return _real_import(name, *args, **kwargs)

    def test_noop_no_logfire_no_endpoint(self):
        env = {
            k: v
            for k, v in __import__("os").environ.items()
            if k != "OTEL_EXPORTER_OTLP_ENDPOINT"
        }

        with (
            patch("builtins.__import__", side_effect=self._block_logfire),
            patch.dict("os.environ", env, clear=True),
            patch("mi.core.utils.telemetry.trace") as mock_trace,
        ):
            bootstrap_telemetry()

            mock_trace.set_tracer_provider.assert_not_called()
        assert telemetry_mod._bootstrapped is True


# ---------------------------------------------------------------------------
# NOTE: PipelineConfig.bootstrap_otel
# ---------------------------------------------------------------------------


class TestPipelineConfigBootstrapOtel:
    """The ``bootstrap_otel`` field on PipelineConfig controls whether the
    CLI / orchestrator should auto-initialise telemetry."""

    def test_defaults_to_true(self):
        from mi.core.pipeline import PipelineConfig

        assert PipelineConfig().bootstrap_otel is True

    def test_can_be_set_false(self):
        from mi.core.pipeline import PipelineConfig

        config = PipelineConfig(bootstrap_otel=False)
        assert config.bootstrap_otel is False

    def test_round_trips_through_model_dump(self):
        from mi.core.pipeline import PipelineConfig

        config = PipelineConfig(bootstrap_otel=False)
        dumped = config.model_dump()
        restored = PipelineConfig(**dumped)
        assert restored.bootstrap_otel is False

    def test_excluded_from_unset_when_default(self):
        from mi.core.pipeline import PipelineConfig

        config = PipelineConfig()
        unset_dump = config.model_dump(exclude_unset=True)
        assert "bootstrap_otel" not in unset_dump


# ---------------------------------------------------------------------------
# NOTE: Orchestrator subprocess telemetry bootstrap
# ---------------------------------------------------------------------------


class TestOrchestratorSubprocessBootstrap:
    """The orchestrator's ``_run_pipeline_in_subprocess`` should bootstrap
    telemetry in child processes, respecting the ``bootstrap_otel`` flag
    and custom hooks."""

    def test_calls_bootstrap_when_no_hook_and_flag_true(self):
        """Default case: no custom hook, bootstrap_otel=True."""
        from mi.core.pipeline_orchestrator import _run_pipeline_in_subprocess
        import mi.core.pipeline_orchestrator as orch_mod

        # Stash original hook and ensure it's None
        original_hook = orch_mod._subprocess_telemetry_hook
        orch_mod._subprocess_telemetry_hook = None

        mock_builder = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.return_value = MagicMock()
        mock_receipt = MagicMock()

        # Mock the pipeline execution chain
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_receipt
        mock_builder_copy = MagicMock()
        mock_builder_copy.build.return_value = mock_pipeline

        try:
            with (
                patch("mi.core.pipeline_orchestrator.bootstrap_telemetry") as mock_bt,
                patch(
                    "mi.core.pipeline_orchestrator.copy.deepcopy",
                    return_value=mock_builder_copy,
                ),
                patch(
                    "mi.core.pipeline_orchestrator._get_or_create_process_span"
                ) as mock_span,
                patch("mi.core.pipeline_orchestrator.trace"),
                patch("mi.core.pipeline_orchestrator.get_tracer"),
            ):
                mock_span.return_value = MagicMock()
                _run_pipeline_in_subprocess(
                    mock_builder, mock_adapter, "item-1", {}, bootstrap_otel=True
                )

            mock_bt.assert_called_once()
        finally:
            orch_mod._subprocess_telemetry_hook = original_hook

    def test_skips_bootstrap_when_flag_false(self):
        """When bootstrap_otel=False, bootstrap_telemetry() is NOT called."""
        from mi.core.pipeline_orchestrator import _run_pipeline_in_subprocess
        import mi.core.pipeline_orchestrator as orch_mod

        original_hook = orch_mod._subprocess_telemetry_hook
        orch_mod._subprocess_telemetry_hook = None

        mock_builder = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.return_value = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock()
        mock_builder_copy = MagicMock()
        mock_builder_copy.build.return_value = mock_pipeline

        try:
            with (
                patch("mi.core.pipeline_orchestrator.bootstrap_telemetry") as mock_bt,
                patch(
                    "mi.core.pipeline_orchestrator.copy.deepcopy",
                    return_value=mock_builder_copy,
                ),
                patch(
                    "mi.core.pipeline_orchestrator._get_or_create_process_span"
                ) as mock_span,
                patch("mi.core.pipeline_orchestrator.trace"),
                patch("mi.core.pipeline_orchestrator.get_tracer"),
            ):
                mock_span.return_value = MagicMock()
                _run_pipeline_in_subprocess(
                    mock_builder, mock_adapter, "item-1", {}, bootstrap_otel=False
                )

            mock_bt.assert_not_called()
        finally:
            orch_mod._subprocess_telemetry_hook = original_hook

    def test_custom_hook_takes_priority(self):
        """When a custom hook is registered, it runs instead of bootstrap_telemetry()."""
        from mi.core.pipeline_orchestrator import _run_pipeline_in_subprocess
        import mi.core.pipeline_orchestrator as orch_mod

        custom_hook = MagicMock()
        original_hook = orch_mod._subprocess_telemetry_hook
        orch_mod._subprocess_telemetry_hook = custom_hook

        mock_builder = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.return_value = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock()
        mock_builder_copy = MagicMock()
        mock_builder_copy.build.return_value = mock_pipeline

        try:
            with (
                patch("mi.core.pipeline_orchestrator.bootstrap_telemetry") as mock_bt,
                patch(
                    "mi.core.pipeline_orchestrator.copy.deepcopy",
                    return_value=mock_builder_copy,
                ),
                patch(
                    "mi.core.pipeline_orchestrator._get_or_create_process_span"
                ) as mock_span,
                patch("mi.core.pipeline_orchestrator.trace"),
                patch("mi.core.pipeline_orchestrator.get_tracer"),
            ):
                mock_span.return_value = MagicMock()
                _run_pipeline_in_subprocess(
                    mock_builder, mock_adapter, "item-1", {}, bootstrap_otel=True
                )

            custom_hook.assert_called_once()
            mock_bt.assert_not_called()
        finally:
            orch_mod._subprocess_telemetry_hook = original_hook

    def test_custom_hook_runs_even_when_bootstrap_otel_false(self):
        """Custom hook is always honoured, regardless of bootstrap_otel flag."""
        from mi.core.pipeline_orchestrator import _run_pipeline_in_subprocess
        import mi.core.pipeline_orchestrator as orch_mod

        custom_hook = MagicMock()
        original_hook = orch_mod._subprocess_telemetry_hook
        orch_mod._subprocess_telemetry_hook = custom_hook

        mock_builder = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.return_value = MagicMock()
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = MagicMock()
        mock_builder_copy = MagicMock()
        mock_builder_copy.build.return_value = mock_pipeline

        try:
            with (
                patch("mi.core.pipeline_orchestrator.bootstrap_telemetry") as mock_bt,
                patch(
                    "mi.core.pipeline_orchestrator.copy.deepcopy",
                    return_value=mock_builder_copy,
                ),
                patch(
                    "mi.core.pipeline_orchestrator._get_or_create_process_span"
                ) as mock_span,
                patch("mi.core.pipeline_orchestrator.trace"),
                patch("mi.core.pipeline_orchestrator.get_tracer"),
            ):
                mock_span.return_value = MagicMock()
                _run_pipeline_in_subprocess(
                    mock_builder, mock_adapter, "item-1", {}, bootstrap_otel=False
                )

            custom_hook.assert_called_once()
            mock_bt.assert_not_called()
        finally:
            orch_mod._subprocess_telemetry_hook = original_hook


# ---------------------------------------------------------------------------
# NOTE: Orchestrator _run_process reads bootstrap_otel from builder config
# ---------------------------------------------------------------------------


class TestOrchestratorPassesBootstrapFlag:
    """The orchestrator's ``_run_process`` should read ``bootstrap_otel``
    from the builder's config and forward it to subprocesses."""

    def test_passes_true_by_default(self):
        from mi.core.pipeline import PipelineConfig
        from mi.core.pipeline_orchestrator import (
            PipelineOrchestrator,
            OrchestratorConfig,
        )
        from mi.core.pipeline_builder import PipelineBuilder

        builder = PipelineBuilder()
        builder._config = PipelineConfig()

        orchestrator = PipelineOrchestrator()
        orchestrator._config = OrchestratorConfig(runtime="process", max_workers=1)
        orchestrator._builder = builder
        orchestrator._adapter = lambda x: PipelineConfig(name=str(x))

        with patch(
            "mi.core.pipeline_orchestrator.ProcessPoolExecutor"
        ) as mock_pool_cls:
            mock_executor = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock()
            # as_completed returns nothing so the loop doesn't execute
            with patch("mi.core.pipeline_orchestrator.as_completed", return_value=[]):
                orchestrator._run_process(
                    ["item-1"], max_workers=1, error_action="stop"
                )

            # Check that submit was called with bootstrap flags
            submit_call = mock_executor.submit.call_args
            assert submit_call is not None
            # positional args: func, builder, adapter, item, trace_carrier,
            #                   bootstrap_env (5), bootstrap_otel (6), environment (7)
            assert submit_call[0][5] is True  # bootstrap_env
            assert submit_call[0][6] is True  # bootstrap_otel

    def test_passes_false_when_config_opts_out(self):
        from mi.core.pipeline import PipelineConfig
        from mi.core.pipeline_orchestrator import (
            PipelineOrchestrator,
            OrchestratorConfig,
        )
        from mi.core.pipeline_builder import PipelineBuilder

        builder = PipelineBuilder()
        builder._config = PipelineConfig(bootstrap_otel=False)

        orchestrator = PipelineOrchestrator()
        orchestrator._config = OrchestratorConfig(runtime="process", max_workers=1)
        orchestrator._builder = builder
        orchestrator._adapter = lambda x: PipelineConfig(name=str(x))

        with patch(
            "mi.core.pipeline_orchestrator.ProcessPoolExecutor"
        ) as mock_pool_cls:
            mock_executor = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_executor)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_executor.submit.return_value = MagicMock()
            with patch("mi.core.pipeline_orchestrator.as_completed", return_value=[]):
                orchestrator._run_process(
                    ["item-1"], max_workers=1, error_action="stop"
                )

            submit_call = mock_executor.submit.call_args
            assert submit_call is not None
            assert submit_call[0][5] is True  # bootstrap_env (still default True)
            assert submit_call[0][6] is False  # bootstrap_otel
