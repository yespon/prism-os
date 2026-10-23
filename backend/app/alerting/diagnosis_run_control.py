"""Current-authority wait and observed interruption of an originally owned run."""

import asyncio
import re
from dataclasses import dataclass

from app.platform.execution.trust import ThreadBindingRepository
from deerflow.runtime import ExecutionTrustError


@dataclass(frozen=True)
class InterruptionResult:
    status: str
    run_ids: tuple[str, ...] = ()
    # Stopping the graph never establishes the absence of outside effects.
    external_effects: str = "unknown"


class DiagnosisStopRequested(ExecutionTrustError):
    """An original incident cancellation intent prevents new tool admission."""


class DiagnosisAuthorityWithdrawn(ExecutionTrustError):
    def __init__(self, result):
        super().__init__("Diagnosis authority withdrawn; interruption " + result.status + "; inspect external effects")
        self.interruption = result


async def interrupt_owned_runs(client, thread, tenant, actor, factory, *, timeout=3):
    """Cleanup retains its original owner proof even after member withdrawal.

    This does not grant new execution. An unavailable binding or transport
    never becomes a confirmed cancellation and must not cause blind retries.
    """
    run_ids = []
    try:
        if not isinstance(thread, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", thread):
            return InterruptionResult("unknown")
        async with asyncio.timeout(timeout):
            await ThreadBindingRepository(factory).get(thread, tenant, actor)
            runs = []
            for status in ("running", "pending"):
                rows = await client.runs.list(thread, limit=100, status=status)
                if not isinstance(rows, list) or len(rows) >= 100:
                    return InterruptionResult("unknown")
                runs.extend(rows)
            for row in runs:
                if not isinstance(row, dict) or not isinstance(row.get("run_id"), str) or not row["run_id"]:
                    return InterruptionResult("unknown", tuple(run_ids))
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", row["run_id"]):
                    return InterruptionResult("unknown", tuple(run_ids))
                if row.get("thread_id", thread) != thread:
                    return InterruptionResult("unknown", tuple(run_ids))
                if row["run_id"] not in run_ids:
                    run_ids.append(row["run_id"])
            if not run_ids:
                # An empty active list does not prove our wait request never
                # created a run, particularly after a lost response.
                return InterruptionResult("unknown")
            for run_id in run_ids:
                await ThreadBindingRepository(factory).get(thread, tenant, actor)
                await client.runs.cancel(thread, run_id, action="interrupt")
            while True:
                await ThreadBindingRepository(factory).get(thread, tenant, actor)
                states = [await client.runs.get(thread, run_id) for run_id in run_ids]
                if any(not isinstance(row, dict) or row.get("run_id") != run_id or row.get("thread_id") != thread for run_id, row in zip(run_ids, states, strict=True)):
                    return InterruptionResult("unknown", tuple(run_ids))
                if all(row.get("status") == "interrupted" for row in states):
                    return InterruptionResult("confirmed", tuple(run_ids))
                if any(isinstance(row, dict) and row.get("status") in {"success", "error", "timeout"} for row in states):
                    return InterruptionResult("unknown", tuple(run_ids))
                await asyncio.sleep(0.05)
    except Exception:
        return InterruptionResult("unknown", tuple(run_ids))


async def wait_authorized_result(wait_coro, validate, interrupt, *, interval=0.25):
    # Do not schedule the remote request until current admission succeeds.
    try:
        await validate()
    except BaseException:
        if asyncio.iscoroutine(wait_coro):
            wait_coro.close()
        raise
    pending = asyncio.ensure_future(wait_coro)
    try:
        while True:
            await validate()
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if done:
                result = pending.result()
                await validate()
                return result
    except DiagnosisStopRequested:
        # The request owner already handles interruption and its unknown
        # outcome. Do not turn that intent into a second remote attempt.
        raise
    except ExecutionTrustError:
        # Dropping the local wait does not establish that the remote run stops.
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        outcome = await interrupt()
        raise DiagnosisAuthorityWithdrawn(outcome) from None
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
