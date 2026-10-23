"""Network input must not bypass pinned hashes or mutate existing output."""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import octop_source_fetch as fetcher  # noqa: E402

REVISION = "e473dd3c4a4741618ffde1a42a3492341a189e8e"


def test_rejects_unpinned_revision_before_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("untrusted input reached network")

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", forbidden)
    with pytest.raises(ValueError, match="independently pinned"):
        fetcher.fetch("unknown", "b5", tmp_path / "out")


def test_preserves_nonempty_output(tmp_path, monkeypatch):
    output = tmp_path / "out"
    output.mkdir()
    (output / "kept").write_text("keep")
    with pytest.raises(ValueError, match="empty"):
        fetcher.fetch(REVISION, "b5", output)
    assert (output / "kept").read_text() == "keep"


def test_rejects_corrupt_download_without_retaining_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"corrupt artifact"))
    with pytest.raises(ValueError, match="original archive digest"):
        fetcher.fetch(REVISION, "b5", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_rejects_oversized_download_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(fetcher, "MAX_ARCHIVE_BYTES", 3)
    monkeypatch.setattr(fetcher.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b"four"))
    with pytest.raises(ValueError, match="size limit"):
        fetcher.fetch(REVISION, "b5", tmp_path / "out")
    assert not (tmp_path / "out").exists()
