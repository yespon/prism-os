# PrismOS release

## Version

- Version/tag:
- Release date:

## Compatibility/removal boundary

- Supported compatibility window: `0.2.x`
- Runtime compatibility removal:

## Migration command

```bash
uv run python scripts/migrate_prismos_home.py --source <preserved-source> --target ~/.prismos --apply
```

Use canonical `PRISMOS_*` inputs for new deployments.

## Rollback

Describe the preserved source, the `PRISMOS_HOME` rollback value, and the
verification performed before switching traffic back.

## Verification evidence

- Brand identity gate:
- Backend tests:
- Frontend gates:
- Migration manifest/checksum:
- `git diff --check`:

## Image/package coordinates

- Repository: `yespon/prism-os`
- Image: `ghcr.io/yespon/prism-os`
- Python package: `prismos`
- Frontend package: `prismos-frontend`

## Known limitations

Document read-only remote resource detection, supported migration scope, and
any alpha limitations.

## Breaking changes

List removed inputs, API or behavior changes, and the operator action required.
