# Pinned Octop upstream

`upstream.tar.gz` retains the complete public main-repository source at the fixed commit in `manifest.json`, including original tests, clients, docs and license. It is source material, not a second running Octop server. External Octop packages are **not** included or enabled.

`manifest.json` records every regular archive member hash and every byte-identical file selected into the host-neutral capability package. Adapter and catalog implementation remain outside those original files. Runtime imports only the four explicitly selected pure modules, never bundled plugins or scripts.

Run `python3 scripts/octop_sync.py verify`. To evaluate a new archive without changing the baseline: `python3 scripts/octop_sync.py compare --archive /path/to/source.tar.gz --revision COMMIT --release TAG --output /tmp/octop-candidate.json`. An accepted version is imported with the same options and the `import` command, then passes the build and migration gates. Keep the commit, artifact digest and MIT notice; never update the baseline merely because a candidate diff exists.

The initial user path imports expert/sub-agent prompt templates and MBTI into existing tenant-scoped CustomAgents. Bundled skills/scripts remain source-only until separately integrated and authorized. Full current capability parity remains an implementation target, not a statement inferred from storing this archive.
