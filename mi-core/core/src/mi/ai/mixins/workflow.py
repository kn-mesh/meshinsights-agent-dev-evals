"""Workflow mixin for single-call LLM processing with structured output."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mi.ai.backends.base import WorkflowRequest
from mi.ai.mixins.base import AIProcessorMixin, OutputT, PDO

if TYPE_CHECKING:
    from mi.core.pipeline import PipelineMetadata


class AIWorkflowMixin(AIProcessorMixin[PDO, OutputT]):
    """Mixin for one-shot structured AI workflow execution."""

    def process(
        self, data_object: PDO, *, metadata: "PipelineMetadata | None" = None
    ) -> None:
        try:
            backend = self._resolve_backend()
            request = WorkflowRequest(
                model=self._resolve_model_ref(),
                system_prompt=self._build_system_prompt(data_object),
                user_message=self._resolve_user_message(data_object),
                output_schema=self._get_output_schema(),
                reasoning_spec=self._get_reasoning_spec(),
                reasoning_effort=self._get_reasoning_effort(),
                transport_retries=self._get_transport_retries(),
                output_retries=self._get_effective_output_retries(),
                usage_limits=self._get_usage_limits(request_limit=None),
                timeout=self._get_timeout(),
                provider_options=self._get_provider_options(),
                backend_options=self._get_backend_options(),
                capture_review=self._review_capture_enabled(metadata),
            )

            self.logger.info(
                f"AI workflow: model={request.model.canonical()}, backend={self.config.backend}, transport_retries={request.transport_retries}, output_retries={request.output_retries}"
            )

            result = backend.run_workflow(request)

            if request.capture_review:
                self._attach_review(data_object, result.review)

            if self._should_attach_response():
                self._attach_response(data_object, result.output)
            if self._should_attach_usage():
                self._attach_usage(data_object, result.usage)
                self.logger.info(
                    f"AI usage: input={result.usage.input_tokens}, output={result.usage.output_tokens}"
                )

        except Exception as exc:
            review = getattr(exc, "review", None)
            if isinstance(review, dict) and self._review_capture_enabled(metadata):
                self._attach_review(data_object, review)
            raise self._normalize_error(exc, "Workflow") from exc
