"""Process-stage telemetry survives processor and downstream failures."""

import logging

from mi.core.objects import ProcessDataObject
from mi.core.pipeline import Pipeline, PipelineConfig, PipelineMetadata
from mi.core.pipeline_receipt import PipelineReceipt
from mi.core.processors import BaseProcessor


class _TelemetryProcessObject(ProcessDataObject):
    def get_execution_telemetry(self) -> dict[str, object]:
        return {"usage": {"requests": 1}}


class _FailingProcessor(BaseProcessor[ProcessDataObject]):
    def process(
        self,
        data_object: ProcessDataObject,
        *,
        metadata: PipelineMetadata | None = None,
    ) -> None:
        _ = data_object
        _ = metadata
        raise RuntimeError("later processor failure")


def test_process_stage_retains_telemetry_when_processor_fails() -> None:
    pipeline = object.__new__(Pipeline)
    pipeline.processors = [_FailingProcessor()]
    pipeline.config = PipelineConfig(name="test", error_action="continue")
    pipeline.logger = logging.getLogger("test-process-telemetry")
    pipeline.receipt = PipelineReceipt(pipeline_id="test")

    process_object = _TelemetryProcessObject()
    process_object.normalized_data["input"] = True
    process_object.set_artifact(
        "processor_model_review", {"request": {"system_prompt": "inspect"}}
    )
    pipeline._stage_process(process_object)

    receipt = pipeline.receipt.process_receipt
    assert receipt is not None
    assert receipt.success is False
    assert receipt.metadata["execution_telemetry"] == {"usage": {"requests": 1}}
    assert receipt.metadata["execution_review"] == {
        "processors": {
            "processor_model_review": {"request": {"system_prompt": "inspect"}}
        }
    }
