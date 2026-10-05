"""Nạp bộ tài liệu minh hoạ (src/demo/kb/*.md) vào kho tri thức của một tổ chức.

Tài liệu là dữ liệu mẫu do hệ thống tạo, tiêu đề gắn nhãn "[Minh hoạ]". Tệp bắt đầu bằng `noi-bo-` là tài liệu nội bộ.
"""

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import KbChunk, KbDocument, Organization
from src.services.kb import chunk_text

KB_DIR = Path(__file__).parent / "kb"
DEMO_TAG = "[Minh hoạ]"


async def seed_kb(session: AsyncSession, org: Organization) -> int:
    """Trả về số tài liệu mới nạp (bỏ qua tài liệu đã có cùng nội dung)."""
    added = 0
    for path in sorted(KB_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8").strip()
        checksum = hashlib.sha256(content.encode()).hexdigest()
        exists = (
            await session.execute(
                select(KbDocument.id).where(KbDocument.organization_id == org.id, KbDocument.checksum == checksum)
            )
        ).scalar_one_or_none()
        if exists:
            continue
        title = content.splitlines()[0].lstrip("# ").strip()
        chunks = chunk_text(content)
        doc = KbDocument(
            organization_id=org.id,
            title=f"{DEMO_TAG} {title}",
            visibility="internal" if path.name.startswith("noi-bo-") else "public",
            filename=path.name,
            content_type="text/markdown",
            size_bytes=len(content.encode()),
            char_count=len(content),
            chunk_count=len(chunks),
            status="ready",
            checksum=checksum,
        )
        session.add(doc)
        await session.flush()
        session.add_all(
            KbChunk(organization_id=org.id, document_id=doc.id, ordinal=i, heading=heading, content=body)
            for i, (heading, body) in enumerate(chunks)
        )
        added += 1
    await session.flush()
    return added
