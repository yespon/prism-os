#!/usr/bin/env python3
"""Acquire a pinned source revision and retain only its audited curated view."""

from __future__ import annotations

import argparse
import json
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import octop_sync as sync

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def fetch(revision: str, release: str, output: Path) -> dict:
    if revision not in sync.PINNED_ORIGINS:
        raise ValueError("Revision has no independently pinned origin")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty")
    output.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://codeload.github.com/TencentCloud/Octop/tar.gz/{revision}"
    # Raw source is ephemeral and is never copied to the retained output.
    # CI runners occasionally stall on the codeload download; retry up to
    # three times with backoff before giving up. Digest checking below is
    # unchanged, so a corrupted or partial retry can never pass.
    with tempfile.TemporaryDirectory(prefix="prismos-octop-fetch-") as temporary:
        archive = Path(temporary) / "original.tar.gz"
        last_error: Exception | None = None
        for attempt in range(3):
            archive.write_bytes(b"")
            count = 0
            try:
                with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as stream:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > MAX_ARCHIVE_BYTES:
                            raise ValueError("Source archive exceeds size limit")
                        stream.write(chunk)
                break
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                time.sleep(2 ** attempt)
        else:
            raise ValueError(f"Source archive download failed after retries: {last_error}")
        if sync.digest(archive.read_bytes()) != sync.PINNED_ORIGINS[revision]:
            raise ValueError("Pinned original archive digest mismatch")
        files, hashes, original_digest, exclusions = sync.snapshot(archive, revision)
        retained = sync.curated_archive(files, revision)
        receipt = sync.manifest_for(files, hashes, original_digest, sync.digest(retained), revision, release)
        output.mkdir(parents=True, exist_ok=True)
        (output / "upstream.tar.gz").write_bytes(retained)
        (output / "manifest.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n")
        # Verify the persisted pair using both origin and member receipt anchors.
        sync.snapshot(output / "upstream.tar.gz", revision, output / "manifest.json")
    return {
        "revision": revision,
        "url": url,
        "archive_sha256": original_digest,
        "retained_archive_sha256": receipt["retained_archive_sha256"],
        "retained_files": len(files),
        "excluded_files": len(exclusions),
        "raw_archive_retained": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, choices=tuple(sync.PINNED_ORIGINS))
    parser.add_argument("--release", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(fetch(args.revision, args.release, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
