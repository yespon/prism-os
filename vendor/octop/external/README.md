# Pinned external Octop distributions

The exact versions and original artifact digests come from `uv.lock` inside the pinned main source. Browser, Gateway and Memory are 1.0.0, Harness is 1.0.1. `manifest.json` stores origin/metadata/member-hash receipts and retained archive digests. Browser, Gateway and Memory source/wheel bytes match that lock and retain original root MIT notices.

Harness contains independently restricted PowerPoint material: English has 50 source members and Chinese has one Skill declaring Proprietary. All 51 are excluded from `octop_harness-1.0.1-prismos-source.tar.gz`; the original Harness wheel is not retained. The filtered view is not an installable original distribution. Original digest/member/metadata receipts were verified at fetch time. Offline checks compare retained bytes and metadata against receipts anchored by independent pinned source-member inventory digests. A fetch revalidates the original distribution hash before curation; newly accepted versions require review and updated digest anchors.

Functional PowerPoint targets remain in the capability ledger for independent implementations. Main Office resources have their own exclusions in the main manifest; this external manifest does not replace that policy.

These inputs are not installed, imported or enabled. Harness's core langchain-mcp-adapters >=0.3.0 requirement conflicts with the host lock 0.2.1; `[all]` inherits that core constraint. The resolver failure is recorded, and the host lock/runtime remain unchanged. Evaluate host adapters or versioned workers for subsequent runtime integration.

Run `python3 scripts/octop_external.py verify` and `make octop-inventory`. Exact paths, hashes and exclusions are in the manifests; package MIT declarations do not override independent resource terms.
