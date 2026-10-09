"""Reject changed and unexpected template files before they enter the catalog."""

import shutil

import prismos_octop.catalog as catalog
import pytest


@pytest.mark.parametrize("mutation", ["changed", "unexpected"])
def test_catalog_rejects_unverified_data(tmp_path, monkeypatch, mutation):
    root = tmp_path / "package"
    shutil.copytree(catalog.ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(catalog, "ROOT", root)
    monkeypatch.setattr(catalog, "DATA", root / "data")
    catalog.provenance.cache_clear()
    try:
        if mutation == "changed":
            (root / "data/experts/general-assistant/SOUL.md").write_text("Changed outside source import")
        else:
            (root / "data/experts/general-assistant/extra.md").write_text("Unverified source")
        with pytest.raises(ValueError, match="Catalog source"):
            catalog.provenance()
    finally:
        catalog.provenance.cache_clear()
