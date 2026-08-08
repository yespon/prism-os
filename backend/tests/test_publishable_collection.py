"""Regression tests for collection-safe backend publishing checks."""

import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_debug_llm_probe_is_safe_to_import_during_pytest_collection() -> None:
    """Importing the tracked probe must not execute an LLM request."""
    result = subprocess.run(
        [sys.executable, "-c", "import test_msg; assert not hasattr(test_msg, 'test')"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DICT:" not in result.stdout


def test_stream_event_is_a_public_value_object() -> None:
    """The existing e2e/live test contract can import and inspect events."""
    from deerflow.client import StreamEvent

    event = StreamEvent(type="end", data={})

    assert event.type == "end"
    assert event.data == {}
