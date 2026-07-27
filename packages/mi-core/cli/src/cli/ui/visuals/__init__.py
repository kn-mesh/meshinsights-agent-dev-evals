"""Composable ASCII-art progress visuals.

Each sub-module exposes ``build_progress()`` and
``build_progress_complete()`` with identical signatures, so callers can
swap visual themes by changing a single import.

Available visuals:

* **conveyor** — boxes on a conveyor belt with rollers.
* **factory** — hopper → factory → rocket pipeline connected by trucks.

The ``deploy`` module contains the end-of-wizard rocket-launch
animation (independent of the progress-bar visual).
"""
# ruff: noqa: F401

from .conveyor import (
    ART_CHROME as CONVEYOR_ART_CHROME,
    ART_HEIGHT as CONVEYOR_ART_HEIGHT,
    build_progress as build_conveyor_progress,
    build_progress_complete as build_conveyor_progress_complete,
)
from .deploy import animate_deploy
from .factory import (
    ART_CHROME as FACTORY_ART_CHROME,
    ART_HEIGHT as FACTORY_ART_HEIGHT,
    build_progress as build_factory_progress,
    build_progress_complete as build_factory_progress_complete,
)
from .progress import COMPACT_CHROME, build_compact, should_use_compact
