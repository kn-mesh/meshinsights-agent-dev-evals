"""Regression test for MES-77: monitor.css must be included in the built CLI wheel.

The bug: ``cli/pyproject.toml`` did not declare ``monitor.css`` as package-data,
so the built wheel omitted it.  Because ``cli/ui/theme.py`` loads the file eagerly
at import time (``MONITOR_CSS = _load_monitor_css()``), *any* import of the CLI
package raised ``FileNotFoundError`` and ``mi auth`` was completely broken.

This test builds the wheel and inspects its contents to guarantee the fix stays
in place.
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


_CLI_DIR = Path(__file__).resolve().parents[2] / "cli"


def test_built_wheel_contains_monitor_css(tmp_path: Path) -> None:
    """Build the CLI wheel and verify cli/ui/monitor.css is inside it."""
    dist = tmp_path / "dist"

    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist)],
        cwd=_CLI_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Wheel build failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    wheels = list(dist.glob("*.whl"))
    assert len(wheels) == 1, f"Expected exactly one wheel, found: {wheels}"

    with zipfile.ZipFile(wheels[0]) as whl:
        names = whl.namelist()

    css_entries = [n for n in names if n.endswith("monitor.css")]
    assert css_entries, (
        f"monitor.css not found in wheel {wheels[0].name}. "
        f"Wheel contents:\n" + "\n".join(names) + "\n\n"
        "This is the MES-77 regression — cli/pyproject.toml must declare "
        "monitor.css in [tool.setuptools.package-data]."
    )
