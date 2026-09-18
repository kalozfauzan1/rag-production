"""Test job runner dan penentuan status."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.jobs import PROCESS_STARTED_AT, STALE_ERROR, JobRunner, resolve_status
from tests.test_store import make_meta


async def test_wait_returns_after_job_finishes() -> None:
    runner = JobRunner()
    done = False

    async def job() -> None:
        nonlocal done
        await asyncio.sleep(0.01)
        done = True

    runner.submit("dokumen", job())
    await runner.wait("dokumen")

    assert done is True
    assert runner.is_running("dokumen") is False


def test_resolve_status_flags_orphan_job_as_failed() -> None:
    meta = make_meta(status="processing")
    meta.updated_at = PROCESS_STARTED_AT - timedelta(minutes=5)

    resolved = resolve_status(meta, running=False)

    assert resolved.status == "failed"
    assert resolved.error == STALE_ERROR


def test_resolve_status_keeps_running_job_processing() -> None:
    meta = make_meta(status="processing")
    meta.updated_at = PROCESS_STARTED_AT - timedelta(minutes=5)

    assert resolve_status(meta, running=True).status == "processing"


def test_resolve_status_leaves_completed_untouched() -> None:
    meta = make_meta(status="completed")
    meta.updated_at = datetime.now(UTC) - timedelta(days=3)

    assert resolve_status(meta, running=False).status == "completed"
