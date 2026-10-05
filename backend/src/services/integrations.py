"""Tích hợp với hệ thống bên ngoài: khoá API theo tổ chức, export CSV cho Power BI, đồng bộ LMS và CRM.

Nguyên tắc:
- Khoá có phạm vi (scope) tối thiểu; chỉ lưu băm SHA-256, khoá gốc trả về đúng một lần khi tạo.
- Mỗi khoá có tài khoản dịch vụ riêng (không mật khẩu, không vai trò) để thao tác qua khoá được ghi nhận đúng tác nhân.
- Export cho Power BI đã khử định danh (không họ tên, email, số điện thoại); CRM cần liên hệ nên tách scope riêng.
"""

import csv
import hashlib
import io
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, select, tuple_

from src.errors import NotFoundError, ValidationFailedError
from src.models import (
    AiAssessment,
    Application,
    Cohort,
    CohortClass,
    Competency,
    CompetencyAssessment,
    Enrollment,
    Intake,
    IntegrationKey,
    OrgMembership,
    Track,
    TrackTarget,
    User,
)
from src.services.audit import RequestMeta, write_audit
from src.services.tenancy import OrgDb

SCOPES = ("export.read", "lms.read", "lms.write", "crm.read")
KEY_PREFIX = "thk"


def hash_key(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _key_out(key: IntegrationKey) -> dict[str, Any]:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "scopes": list(key.scopes),
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "revoked_at": key.revoked_at,
    }


# ---------------------------------------------------------------------------------------------------------------------
# Quản lý khoá
# ---------------------------------------------------------------------------------------------------------------------


async def list_keys(db: OrgDb) -> list[dict[str, Any]]:
    keys = (await db.session.execute(select(IntegrationKey).order_by(IntegrationKey.created_at.desc()))).scalars()
    return [_key_out(k) for k in keys]


async def create_key(
    db: OrgDb, *, name: str, scopes: list[str], actor_user_id: uuid.UUID, meta: RequestMeta
) -> tuple[dict[str, Any], str]:
    name = name.strip()
    if not 3 <= len(name) <= 120:
        raise ValidationFailedError("Tên khoá không hợp lệ", {"name": "Từ 3 đến 120 ký tự"})
    wanted = sorted(set(scopes))
    if not wanted or any(s not in SCOPES for s in wanted):
        raise ValidationFailedError("Phạm vi không hợp lệ", {"scopes": f"Chọn trong: {', '.join(SCOPES)}"})

    prefix = secrets.token_hex(4)
    token = f"{KEY_PREFIX}_{prefix}_{secrets.token_urlsafe(32)}"
    user = User(
        email=f"integration.{prefix}@{db.org.slug}.integrations.invalid",
        full_name=f"Tích hợp: {name}",
        password_hash=None,
    )
    db.session.add(user)
    await db.session.flush()
    membership = OrgMembership(organization_id=db.org.id, user_id=user.id, status="active")
    db.session.add(membership)
    await db.session.flush()
    key = IntegrationKey(
        organization_id=db.org.id,
        name=name,
        prefix=prefix,
        key_hash=hash_key(token),
        scopes=wanted,
        service_membership_id=membership.id,
        created_by=actor_user_id,
    )
    db.session.add(key)
    await db.session.flush()
    await db.session.refresh(key)
    write_audit(
        db,
        action="integration.key_created",
        entity_type="integration_key",
        entity_id=key.id,
        actor_user_id=actor_user_id,
        after={"name": name, "prefix": prefix, "scopes": wanted},
        meta=meta,
    )
    return _key_out(key), token


async def revoke_key(db: OrgDb, key_id: uuid.UUID, *, actor_user_id: uuid.UUID, meta: RequestMeta) -> dict[str, Any]:
    key = (await db.session.execute(select(IntegrationKey).where(IntegrationKey.id == key_id))).scalar_one_or_none()
    if key is None:
        raise NotFoundError("Không tìm thấy khoá tích hợp")
    if key.revoked_at is None:
        key.revoked_at = datetime.now(UTC)
        membership = await db.session.get(OrgMembership, key.service_membership_id)
        if membership is not None:
            membership.status = "suspended"
        write_audit(
            db,
            action="integration.key_revoked",
            entity_type="integration_key",
            entity_id=key.id,
            actor_user_id=actor_user_id,
            before={"prefix": key.prefix},
            meta=meta,
        )
    return _key_out(key)


async def authenticate(db: OrgDb, token: str) -> IntegrationKey | None:
    """Khoá còn hiệu lực của tổ chức hiện tại (RLS chỉ cho thấy khoá của tổ chức này), hoặc None."""
    if not token.startswith(f"{KEY_PREFIX}_"):
        return None
    key = (
        await db.session.execute(
            select(IntegrationKey).where(
                IntegrationKey.key_hash == hash_key(token), IntegrationKey.revoked_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if key is not None:
        key.last_used_at = datetime.now(UTC)
    return key


# ---------------------------------------------------------------------------------------------------------------------
# Export CSV cho Power BI (khử định danh)
# ---------------------------------------------------------------------------------------------------------------------


def _csv(header: list[str], rows: list[list[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(["" if v is None else v.isoformat() if isinstance(v, datetime) else v for v in row])
    return "﻿" + out.getvalue()  # BOM để Excel/Power BI đọc đúng UTF-8


def _region(city: str | None) -> str:
    if not city:
        return "khong_khai"
    return {"Hà Nội": "ha_noi", "TP. Hồ Chí Minh": "tp_hcm"}.get(city, "tinh_khac")


async def export_applications(db: OrgDb) -> str:
    ranked = select(
        AiAssessment.application_id,
        AiAssessment.tier,
        AiAssessment.total_score,
        func.row_number()
        .over(partition_by=AiAssessment.application_id, order_by=AiAssessment.created_at.desc())
        .label("rn"),
    ).subquery()
    latest_ai = select(ranked).where(ranked.c.rn == 1).subquery()  # lượt chấm AI mới nhất của mỗi hồ sơ
    rows = (
        await db.session.execute(
            select(
                Application.id,
                Application.candidate_code,
                Intake.id,
                Intake.name,
                Application.status,
                Application.current_round,
                Application.submitted_at,
                Application.updated_at,
                Application.profile["gender"].astext,
                Application.profile["city"].astext,
                latest_ai.c.tier,
                latest_ai.c.total_score,
            )
            .join(Intake, Intake.id == Application.intake_id)
            .outerjoin(latest_ai, latest_ai.c.application_id == Application.id)
            .where(Application.status != "DRAFT")
            .order_by(Application.submitted_at, Application.id)
        )
    ).all()
    header = [
        "application_id", "candidate_code", "intake_id", "intake_name", "status", "current_round", "submitted_at",
        "updated_at", "gender", "region", "ai_tier", "ai_score",
    ]  # fmt: skip
    return _csv(header, [[*r[:8], r[8] or "khong_khai", _region(r[9]), r[10], r[11]] for r in rows])


async def export_enrollments(db: OrgDb) -> str:
    rows = (
        await db.session.execute(
            select(
                Enrollment.id,
                Application.candidate_code,
                Cohort.code,
                Track.key,
                CohortClass.name,
                Enrollment.status,
                Enrollment.enrolled_at,
                Enrollment.qualification_decided_at,
            )
            .join(Application, Application.id == Enrollment.application_id)
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .outerjoin(Track, Track.id == Enrollment.track_id)
            .outerjoin(CohortClass, CohortClass.id == Enrollment.class_id)
            .order_by(Cohort.code, Enrollment.enrolled_at, Enrollment.id)
        )
    ).all()
    header = [
        "enrollment_id",
        "candidate_code",
        "cohort_code",
        "track",
        "class",
        "status",
        "enrolled_at",
        "qualification_decided_at",
    ]
    return _csv(header, [list(r) for r in rows])


async def export_competency_attainment(db: OrgDb) -> str:
    """Một dòng mỗi (học viên, năng lực mục tiêu): mức mục tiêu, mức mới nhất, đạt hay chưa — nguồn cho dashboard chuẩn đầu ra."""
    targets = (
        await db.session.execute(
            select(
                Enrollment.id,
                Cohort.code,
                Track.key,
                Competency.id,
                Competency.code,
                Competency.name,
                TrackTarget.target_level,
                Enrollment.status,
            )
            .join(Cohort, Cohort.id == Enrollment.cohort_id)
            .join(Track, Track.id == Enrollment.track_id)
            .join(TrackTarget, TrackTarget.track_id == Enrollment.track_id)
            .join(Competency, Competency.id == TrackTarget.competency_id)
            .order_by(Cohort.code, Enrollment.id, Competency.code)
        )
    ).all()
    latest: dict[tuple[uuid.UUID, uuid.UUID], tuple[int, datetime, int]] = {}
    for enrollment_id, competency_id, level, assessed_at in (
        await db.session.execute(
            select(
                CompetencyAssessment.enrollment_id,
                CompetencyAssessment.competency_id,
                CompetencyAssessment.level,
                CompetencyAssessment.assessed_at,
            ).order_by(CompetencyAssessment.assessed_at, CompetencyAssessment.id)
        )
    ).all():
        count = latest.get((enrollment_id, competency_id), (0, assessed_at, 0))[2]
        latest[(enrollment_id, competency_id)] = (level, assessed_at, count + 1)
    rows: list[list[Any]] = []
    for enrollment_id, cohort_code, track, comp_id, comp_code, comp_name, target, status in targets:
        hit = latest.get((enrollment_id, comp_id))
        last_level: int | None = hit[0] if hit else None
        last_at: datetime | None = hit[1] if hit else None
        count = hit[2] if hit else 0
        met = None if last_level is None else int(last_level >= target)
        rows.append(
            [enrollment_id, cohort_code, track, status, comp_code, comp_name, target, last_level, met, last_at, count]
        )
    header = [
        "enrollment_id", "cohort_code", "track", "enrollment_status", "competency_code", "competency_name",
        "target_level", "latest_level", "met", "assessed_at", "assessments",
    ]  # fmt: skip
    return _csv(header, rows)


EXPORTS = {
    "applications": export_applications,
    "enrollments": export_enrollments,
    "competency_attainment": export_competency_attainment,
}


# ---------------------------------------------------------------------------------------------------------------------
# LMS
# ---------------------------------------------------------------------------------------------------------------------


async def lms_roster(db: OrgDb, cohort_code: str) -> list[dict[str, Any]]:
    cohort = (await db.session.execute(select(Cohort).where(Cohort.code == cohort_code))).scalar_one_or_none()
    if cohort is None:
        raise NotFoundError("Không tìm thấy khoá học")
    rows = (
        await db.session.execute(
            select(Enrollment, User.email, User.full_name, Application.candidate_code, Track.key, CohortClass.name)
            .join(OrgMembership, OrgMembership.id == Enrollment.membership_id)
            .join(User, User.id == OrgMembership.user_id)
            .join(Application, Application.id == Enrollment.application_id)
            .outerjoin(Track, Track.id == Enrollment.track_id)
            .outerjoin(CohortClass, CohortClass.id == Enrollment.class_id)
            .where(Enrollment.cohort_id == cohort.id)
            .order_by(User.full_name, Enrollment.id)
        )
    ).all()
    return [
        {
            "enrollment_id": e.id,
            "candidate_code": code,
            "email": email,
            "full_name": name,
            "status": e.status,
            "track": track,
            "class_name": klass,
        }
        for e, email, name, code, track, klass in rows
    ]


async def lms_push_assessments(
    db: OrgDb, items: list[dict[str, Any]], *, key: IntegrationKey, meta: RequestMeta
) -> dict[str, Any]:
    """Nhận đánh giá năng lực từ LMS. Idempotent theo `external_ref`: gửi lại cùng mã thì bỏ qua, không tạo trùng."""
    codes = {i["candidate_code"] for i in items}
    enrollments = {
        code: (e_id, status)
        for e_id, code, status in (
            await db.session.execute(
                select(Enrollment.id, Application.candidate_code, Enrollment.status)
                .join(Application, Application.id == Enrollment.application_id)
                .where(Application.candidate_code.in_(codes))
            )
        ).all()
    }
    competencies = {
        c.code: c
        for c in (
            await db.session.execute(
                select(Competency).where(Competency.code.in_({i["competency_code"] for i in items}))
            )
        ).scalars()
    }
    refs = {i["external_ref"] for i in items}
    seen = set(
        (
            await db.session.execute(
                select(CompetencyAssessment.external_ref).where(CompetencyAssessment.external_ref.in_(refs))
            )
        ).scalars()
    )
    created = duplicates = 0
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        ref = item["external_ref"]
        if ref in seen:
            duplicates += 1
            continue
        enrollment = enrollments.get(item["candidate_code"])
        competency = competencies.get(item["competency_code"])
        if enrollment is None:
            errors.append({"index": index, "external_ref": ref, "error": "unknown_candidate"})
            continue
        if competency is None:
            errors.append({"index": index, "external_ref": ref, "error": "unknown_competency"})
            continue
        if not 1 <= item["level"] <= competency.max_level:
            errors.append({"index": index, "external_ref": ref, "error": "level_out_of_range"})
            continue
        db.session.add(
            CompetencyAssessment(
                organization_id=db.org.id,
                enrollment_id=enrollment[0],
                competency_id=competency.id,
                level=item["level"],
                evidence=(item.get("evidence") or "").strip()[:2000] or f"Đồng bộ từ LMS ({key.name})",
                assessor_membership_id=key.service_membership_id,
                assessed_at=item.get("assessed_at") or datetime.now(UTC),
                external_ref=ref,
            )
        )
        seen.add(ref)
        created += 1
    if created:
        write_audit(
            db,
            action="integration.lms_assessments",
            entity_type="integration_key",
            entity_id=key.id,
            after={"created": created, "duplicates": duplicates, "errors": len(errors)},
            meta=meta,
        )
    return {"created": created, "duplicates": duplicates, "errors": errors}


# ---------------------------------------------------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------------------------------------------------


def encode_cursor(updated_at: datetime, app_id: uuid.UUID) -> str:
    return f"{updated_at.isoformat()}|{app_id}"


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        stamp, _, raw = cursor.partition("|")
        return datetime.fromisoformat(stamp), uuid.UUID(raw)
    except ValueError:
        raise ValidationFailedError("Con trỏ không hợp lệ", {"cursor": "Không hợp lệ"}) from None


async def crm_changes(
    db: OrgDb, *, updated_since: datetime | None, cursor: str | None, limit: int, key: IntegrationKey, meta: RequestMeta
) -> dict[str, Any]:
    """Hồ sơ thay đổi theo thời gian (keyset theo updated_at, id) để CRM đồng bộ trạng thái và liên hệ ứng viên."""
    conditions = [Application.status != "DRAFT"]
    if updated_since is not None:
        conditions.append(Application.updated_at >= updated_since)
    if cursor:
        at, app_id = decode_cursor(cursor)
        conditions.append(tuple_(Application.updated_at, Application.id) > tuple_(at, app_id))
    rows = (
        await db.session.execute(
            select(Application, Intake.name, User.email)
            .join(Intake, Intake.id == Application.intake_id)
            .join(OrgMembership, OrgMembership.id == Application.applicant_membership_id)
            .join(User, User.id == OrgMembership.user_id)
            .where(and_(*conditions))
            .order_by(Application.updated_at, Application.id)
            .limit(limit + 1)
        )
    ).all()
    items = [
        {
            "application_id": app.id,
            "candidate_code": app.candidate_code,
            "full_name": (app.profile or {}).get("full_name"),
            "email": email,
            "phone": (app.profile or {}).get("phone"),
            "intake": intake_name,
            "status": app.status,
            "current_round": app.current_round,
            "submitted_at": app.submitted_at,
            "updated_at": app.updated_at,
        }
        for app, intake_name, email in rows[:limit]
    ]
    next_cursor = encode_cursor(rows[limit - 1][0].updated_at, rows[limit - 1][0].id) if len(rows) > limit else None
    write_audit(
        db,
        action="integration.crm_pull",
        entity_type="integration_key",
        entity_id=key.id,
        after={"items": len(items)},
        meta=meta,
    )
    return {"items": items, "next_cursor": next_cursor}
