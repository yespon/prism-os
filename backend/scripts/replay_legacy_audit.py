"""Replay noncritical M1 audit projections for one tenant.

Run from backend: uv run python -m scripts.replay_legacy_audit --tenant TENANT_ID
"""

import argparse
import asyncio

from app.alerting.legacy_audit_delivery import LegacyAuditDeliveryService


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    service = LegacyAuditDeliveryService()
    delivered = await service.replay(args.tenant, limit=args.limit)
    print({"delivered_this_run": delivered, "counts": await service.counts(args.tenant)})


if __name__ == "__main__":
    asyncio.run(main())
