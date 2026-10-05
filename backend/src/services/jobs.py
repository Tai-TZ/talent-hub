"""Tác vụ nền có tiến độ. Chạy trong tiến trình hiện tại bằng asyncio; đủ cho một tổ chức vận hành thông thường.

Ghi chú vận hành: khi cần chịu tải lớn hoặc nhiều tiến trình, chuyển `spawn` sang hàng đợi riêng (arq/Celery);
giao diện bảng `jobs` và API không đổi.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from src.errors import NotFoundError
from src.models import Job
from src.services.tenancy import OrgDb, background_org_db

logger = logging.getLogger(__name__)
_tasks: set[asyncio.Task[None]] = set()


async def create_job(db: OrgDb, *, kind: str, created_by: uuid.UUID | None, params: dict[str, Any]) -> Job:
    job = Job(organization_id=db.org.id, kind=kind, status="queued", params=params, created_by=created_by)
    db.session.add(job)
    await db.session.flush()
    return job


async def get_job(db: OrgDb, job_id: uuid.UUID) -> Job:
    job = (await db.session.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Không tìm thấy tác vụ")
    return job


async def active_job(db: OrgDb, kind: str, key: str, value: str) -> Job | None:
    """Tác vụ cùng loại đang chạy cho cùng đối tượng, để không chạy trùng."""
    rows = (
        (await db.session.execute(select(Job).where(Job.kind == kind, Job.status.in_(("queued", "running")))))
        .scalars()
        .all()
    )
    return next((j for j in rows if (j.params or {}).get(key) == value), None)


def spawn(
    org_id: uuid.UUID, job_id: uuid.UUID, work: Callable[[uuid.UUID, uuid.UUID], Awaitable[dict[str, Any]]]
) -> None:
    """Chạy `work(org_id, job_id)` nền và ghi trạng thái cuối vào bảng jobs."""

    async def runner() -> None:
        async with background_org_db(org_id) as db:
            await db.session.execute(
                update(Job).where(Job.id == job_id).values(status="running", started_at=datetime.now(UTC))
            )
        try:
            result = await work(org_id, job_id)
            status, error = "done", None
        except Exception as exc:  # noqa: BLE001 - mọi lỗi đều phải được ghi lại vào job thay vì làm sập tiến trình
            logger.exception("job failed", extra={"job_id": str(job_id)})
            result, status, error = {}, "failed", str(exc)[:500]
        async with background_org_db(org_id) as db:
            await db.session.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status=status, result=result, error=error, finished_at=datetime.now(UTC))
            )

    task = asyncio.create_task(runner())
    _tasks.add(task)  # giữ tham chiếu để không bị thu gom khi đang chạy
    task.add_done_callback(_tasks.discard)


async def set_progress(org_id: uuid.UUID, job_id: uuid.UUID, *, done: int, total: int | None = None) -> None:
    values: dict[str, Any] = {"done": done}
    if total is not None:
        values["total"] = total
    async with background_org_db(org_id) as db:
        await db.session.execute(update(Job).where(Job.id == job_id).values(**values))


async def wait_for_all() -> None:
    """Dùng trong test và khi tắt ứng dụng: đợi các tác vụ nền đang chạy xong."""
    if _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)
