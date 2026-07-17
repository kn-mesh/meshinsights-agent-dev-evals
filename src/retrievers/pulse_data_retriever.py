"""Retrieve Pulse alarm evidence from MongoDB or a deterministic snapshot."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from mi.core.pipeline import PipelineMetadata
from mi.core.retrievers import BaseRetriever, BaseRetrieverConfig
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError
from pydantic import Field

from src.objects.pipeline_metadata import PulseFailureAnalysisMetadata

_SNAPSHOT_MODES = {"off", "use", "refresh", "strict"}


class PulseAlarmTemperatureHistoryRetrieverConfig(BaseRetrieverConfig):
    """Configure Pulse evidence retrieval and optional local snapshots."""

    name: str = "mongo"
    scope: str = "pulse_alarm_temperature_history"
    lookback_days: int = Field(default=365, ge=1)
    post_alarm_hours: int = Field(default=0, ge=0)
    keep_all_post_alarm_rows: bool = False
    alarms_collection: str = "alarms"
    telemetry_collection: str = "sensordatas"
    sensor_devices_collection: str = "sensordevices"
    steam_trap_devices_collection: str = "steamtrapdevices"
    snapshot_mode: str = "off"
    snapshot_dir: str | None = None


class PulseAlarmTemperatureHistoryRetriever(BaseRetriever):
    """Retrieve the latest eligible FDE alarm and its historical evidence window."""

    config: PulseAlarmTemperatureHistoryRetrieverConfig

    def __init__(
        self, config: PulseAlarmTemperatureHistoryRetrieverConfig | None = None
    ) -> None:
        """Initialize the retriever with typed settings."""
        resolved = config or PulseAlarmTemperatureHistoryRetrieverConfig()
        super().__init__(resolved)
        self.config = resolved

    def retrieve(self, *, metadata: PipelineMetadata | None = None) -> dict[str, Any]:
        """Return a portable evidence package for one unit and decision timestamp."""
        typed_metadata = self._validate_metadata(metadata)
        mode = self._snapshot_mode()
        snapshot_path = self._snapshot_path(typed_metadata, mode)
        if mode in {"use", "strict"} and snapshot_path is not None:
            snapshot = self._load_snapshot(snapshot_path)
            if snapshot is not None:
                return snapshot
            if mode == "strict":
                raise FileNotFoundError(
                    f"Retrieval snapshot does not exist: {snapshot_path}"
                )

        payload = self._retrieve_from_mongo(typed_metadata)
        if mode in {"use", "refresh"} and snapshot_path is not None:
            self._write_snapshot(snapshot_path, payload)
        return payload

    def _retrieve_from_mongo(
        self, metadata: PulseFailureAnalysisMetadata
    ) -> dict[str, Any]:
        """Query MongoDB and normalize the result into an evidence package."""
        client = self._create_client()
        try:
            database = client[self._required_env("mongo_database")]
            alarm = self._fetch_latest_alarm(
                database, metadata.sensor_id, metadata.decision_timestamp
            )
            if alarm is None:
                raise ValueError(
                    "No FDE alarm was found at or before the decision timestamp."
                )

            detected_at = alarm["detectedAt"]
            window_start = detected_at - timedelta(days=self.config.lookback_days)
            window_end = detected_at + timedelta(hours=self.config.post_alarm_hours)
            history = self._fetch_temperature_history(
                database, metadata.sensor_id, window_start, window_end
            )
            if not self.config.keep_all_post_alarm_rows:
                history = self._keep_first_post_alarm_point(history, detected_at)
            if not history:
                raise ValueError(
                    "No temperature evidence was found for the selected alarm."
                )

            return {
                "sensor_id": metadata.sensor_id,
                "unit": metadata.unit,
                "decision_timestamp": metadata.decision_timestamp,
                "steam_trap_type": self._fetch_steam_trap_type(
                    database, metadata.sensor_id
                ),
                "selected_alarm": self._serialize_alarm(alarm),
                "window_start": window_start,
                "window_end": window_end,
                "lookback_days": self.config.lookback_days,
                "post_alarm_hours": self.config.post_alarm_hours,
                "temperature_history": history,
            }
        except PyMongoError as error:
            raise RuntimeError(f"Mongo query failed: {error}") from error
        finally:
            client.close()

    def _validate_metadata(
        self, metadata: PipelineMetadata | None
    ) -> PulseFailureAnalysisMetadata:
        """Validate and return the use-case metadata contract."""
        if not isinstance(metadata, PulseFailureAnalysisMetadata):
            raise ValueError("Pipeline metadata must be PulseFailureAnalysisMetadata.")
        return metadata

    def _create_client(self) -> MongoClient[Any]:
        """Create a Mongo client from the established project environment variables."""
        username = quote_plus(self._required_env("mongodb_username"))
        password = quote_plus(self._required_env("mongodb_password"))
        host = self._required_env("mongodb_host")
        if "://" not in host:
            raise ValueError("mongodb_host must include a URI scheme.")
        scheme, remainder = host.split("://", 1)
        database = self._required_env("mongo_database")
        uri = f"{scheme}://{username}:{password}@{remainder}{database}?retryWrites=true&w=majority"
        return MongoClient(uri, serverSelectionTimeoutMS=10000)

    def _fetch_latest_alarm(
        self, database: Database[Any], sensor_id: int, decision_timestamp: datetime
    ) -> dict[str, Any] | None:
        """Return the latest FDE alarm visible at the decision point."""
        return database[self.config.alarms_collection].find_one(
            {
                "sensorIdDec": sensor_id,
                "detectedAt": {"$lte": decision_timestamp},
                "$or": [{"alarmData.type": "FDE"}, {"type": "FDE"}],
            },
            {
                "_id": 1,
                "sensorIdDec": 1,
                "detectedAt": 1,
                "alertType": 1,
                "analystStatus": 1,
                "alarmData.type": 1,
                "alarmData.code": 1,
                "alarmData.description": 1,
            },
            sort=[("detectedAt", DESCENDING)],
        )

    def _fetch_steam_trap_type(
        self, database: Database[Any], sensor_id: int
    ) -> str | None:
        """Resolve the trap type from the latest installation records."""
        sensors = database[self.config.sensor_devices_collection]
        projection = {"sensor": 1, "lastUpdatedAt": 1}
        sensor_device = sensors.find_one(
            {"sensorIdDec": sensor_id, "isDeleted": {"$ne": True}},
            projection,
            sort=[("lastUpdatedAt", DESCENDING)],
        ) or sensors.find_one(
            {"sensorIdDec": sensor_id},
            projection,
            sort=[("lastUpdatedAt", DESCENDING)],
        )
        if sensor_device is None:
            return None
        trap_device = database[self.config.steam_trap_devices_collection].find_one(
            {"sensor": sensor_device["sensor"]},
            {"type": 1},
            sort=[("installedAt", DESCENDING), ("_id", DESCENDING)],
        )
        if trap_device is None or trap_device.get("type") is None:
            return None
        return str(trap_device["type"])

    def _fetch_temperature_history(
        self,
        database: Database[Any],
        sensor_id: int,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        """Return normalized temperature rows ordered by timestamp."""
        cursor = (
            database[self.config.telemetry_collection]
            .find(
                {
                    "metadata.sensorIdDec": sensor_id,
                    "createdAt": {"$gte": window_start, "$lte": window_end},
                },
                {
                    "_id": 1,
                    "createdAt": 1,
                    "pipeTemperature": 1,
                    "condensationTemperature": 1,
                    "frontMic": 1,
                },
            )
            .sort("createdAt", ASCENDING)
        )
        return [
            {
                "telemetry_id": str(row["_id"]),
                "timestamp": row["createdAt"],
                "steam_temperature": row.get("pipeTemperature"),
                "condensate_temperature": row.get("condensationTemperature"),
                "front_mic": row.get("frontMic"),
            }
            for row in cursor
        ]

    def _serialize_alarm(self, alarm: dict[str, Any]) -> dict[str, Any]:
        """Normalize an alarm document into the portable evidence contract."""
        alarm_data = alarm.get("alarmData") or {}
        return {
            "alarm_id": str(alarm["_id"]),
            "sensor_id": alarm["sensorIdDec"],
            "detected_at": alarm["detectedAt"],
            "alert_type": alarm.get("alertType"),
            "analyst_status": alarm.get("analystStatus"),
            "alarm_type": alarm_data.get("type") or alarm.get("type"),
            "alarm_code": alarm_data.get("code"),
            "alarm_description": alarm_data.get("description"),
        }

    def _keep_first_post_alarm_point(
        self, rows: list[dict[str, Any]], detected_at: datetime
    ) -> list[dict[str, Any]]:
        """Prevent hindsight leakage while retaining one chart-continuity point."""
        result: list[dict[str, Any]] = []
        for row in rows:
            result.append(row)
            if row["timestamp"] > detected_at:
                break
        return result

    def _snapshot_mode(self) -> str:
        """Return the validated snapshot mode."""
        mode = self.config.snapshot_mode.strip().lower()
        if mode not in _SNAPSHOT_MODES:
            raise ValueError(
                f"snapshot_mode must be one of: {', '.join(sorted(_SNAPSHOT_MODES))}."
            )
        return mode

    def _snapshot_path(
        self, metadata: PulseFailureAnalysisMetadata, mode: str
    ) -> Path | None:
        """Resolve a deterministic snapshot filename for one example."""
        if mode == "off":
            return None
        if not self.config.snapshot_dir:
            raise ValueError("snapshot_dir is required when snapshot_mode is enabled.")
        timestamp = metadata.decision_timestamp.strftime("%Y%m%dT%H%M%S")
        filename = (
            f"{timestamp}_lb{self.config.lookback_days}_"
            f"pa{self.config.post_alarm_hours}_keep{int(self.config.keep_all_post_alarm_rows)}.json"
        )
        return (
            Path(self.config.snapshot_dir).expanduser().resolve()
            / f"sensor_{metadata.sensor_id}"
            / filename
        )

    def _load_snapshot(self, path: Path) -> dict[str, Any] | None:
        """Load and decode one local evidence snapshot."""
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Snapshot payload must be a JSON object: {path}")
        return self._decode_snapshot(payload)

    def _write_snapshot(self, path: Path, payload: dict[str, Any]) -> None:
        """Atomically persist one portable evidence package."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        temporary_path.write_text(
            json.dumps(self._encode_snapshot(payload), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    def _encode_snapshot(self, value: Any) -> Any:
        """Recursively encode datetimes for stable JSON snapshots."""
        if isinstance(value, datetime):
            return {"__type__": "datetime", "value": value.isoformat()}
        if isinstance(value, dict):
            return {
                str(key): self._encode_snapshot(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._encode_snapshot(item) for item in value]
        return value

    def _decode_snapshot(self, value: Any) -> Any:
        """Recursively restore datetime values from stable JSON snapshots."""
        if isinstance(value, dict):
            if value.get("__type__") == "datetime":
                encoded = value.get("value")
                if not isinstance(encoded, str):
                    raise ValueError("Encoded snapshot datetime must be a string.")
                return datetime.fromisoformat(encoded)
            return {key: self._decode_snapshot(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._decode_snapshot(item) for item in value]
        return value

    def _required_env(self, key: str) -> str:
        """Return one required environment variable."""
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Missing required environment variable: {key}")
        return value
