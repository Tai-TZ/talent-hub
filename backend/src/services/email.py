"""Email qua hàng đợi (outbox): ghi cùng transaction nghiệp vụ, gửi nền, thử lại khi lỗi.

Backend: `console` (ghi log, dùng khi phát triển), `smtp` (Mailpit khi local hoặc máy chủ thật), `none` (tắt).
"""

import asyncio
import logging
import smtplib
import ssl
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Protocol

from sqlalchemy import select

from src.config import Settings, get_settings
from src.models import EmailOutbox
from src.services.tenancy import OrgDb, background_org_db

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5


class EmailBackend(Protocol):
    name: str

    async def send(self, to: str, subject: str, body: str) -> None: ...


class ConsoleBackend:
    name = "console"

    async def send(self, to: str, subject: str, body: str) -> None:
        logger.info("email (console)", extra={"to": to, "subject": subject})


class SmtpBackend:
    name = "smtp"

    def __init__(self, settings: Settings) -> None:
        self.s = settings

    def _send(self, to: str, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.s.email_from, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=10) as smtp:
            if self.s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if self.s.smtp_user:
                smtp.login(self.s.smtp_user, self.s.smtp_password or "")
            smtp.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send, to, subject, body)


class NullBackend:
    name = "none"

    async def send(self, to: str, subject: str, body: str) -> None:
        return None


def get_backend(settings: Settings) -> EmailBackend:
    if settings.email_backend == "smtp":
        return SmtpBackend(settings)
    if settings.email_backend == "none":
        return NullBackend()
    return ConsoleBackend()


def enqueue(db: OrgDb, *, to: str, subject: str, body: str) -> None:
    db.session.add(EmailOutbox(organization_id=db.org.id, to_email=to, subject=subject, body=body))


async def flush_outbox(org_id: uuid.UUID, backend: EmailBackend | None = None) -> int:
    """Gửi các email đang chờ của một tổ chức; trả về số email đã gửi. Hàng bị khoá để không gửi trùng."""
    backend = backend or get_backend(get_settings())
    sent = 0
    async with background_org_db(org_id) as db:
        rows = (
            (
                await db.session.execute(
                    select(EmailOutbox)
                    .where(EmailOutbox.status == "pending", EmailOutbox.attempts < MAX_ATTEMPTS)
                    .order_by(EmailOutbox.created_at)
                    .limit(50)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.attempts += 1
            try:
                await backend.send(row.to_email, row.subject, row.body)
                row.status, row.sent_at, row.last_error = "sent", datetime.now(UTC), None
                sent += 1
            except Exception as exc:  # noqa: BLE001 - lỗi gửi được ghi lại để thử lại, không làm hỏng luồng nghiệp vụ
                row.last_error = str(exc)[:300]
                if row.attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
    return sent
