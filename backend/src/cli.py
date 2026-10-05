"""CLI vận hành nền tảng. Chạy bằng vai trò chủ sở hữu bảng (MIGRATION_DATABASE_URL).

python -m src.cli org create --slug northwind --name "Northwind University" --admin-email a@b.c
python -m src.cli seed-dev
"""

import argparse
import asyncio
import secrets
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import get_settings
from src.db import set_org_context
from src.models import AuditLog, Organization, OrgMembership, Role, User, UserRole
from src.services.security import hash_password

DEV_PASSWORD = "Passw0rd!dev"
SEED_ORGS = {"northwind": "Northwind University", "demo-uni": "Demo University"}
ALL_ROLES = [
    "applicant",
    "reviewer",
    "approver",
    "cohort_manager",
    "training_manager",
    "mentor",
    "admin",
]


async def create_org(session: AsyncSession, *, slug: str, name: str, locale: str = "vi") -> Organization:
    existing = (await session.execute(select(Organization).where(Organization.slug == slug))).scalar_one_or_none()
    if existing is not None:
        return existing
    org = Organization(slug=slug, name=name, default_locale=locale)
    session.add(org)
    await session.flush()
    await set_org_context(session, org.id)
    session.add(
        AuditLog(
            organization_id=org.id,
            action="org.created",
            entity_type="organization",
            entity_id=str(org.id),
            after={"slug": slug, "name": name},
        )
    )
    return org


async def add_member(
    session: AsyncSession,
    org: Organization,
    *,
    email: str,
    full_name: str,
    role_codes: list[str],
    password: str,
    must_change_password: bool,
) -> User:
    await set_org_context(session, org.id)
    user = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
    if user is None:
        user = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            must_change_password=must_change_password,
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
    membership = (
        await session.execute(
            select(OrgMembership).where(OrgMembership.organization_id == org.id, OrgMembership.user_id == user.id)
        )
    ).scalar_one_or_none()
    if membership is None:
        membership = OrgMembership(organization_id=org.id, user_id=user.id, status="active")
        session.add(membership)
        await session.flush()
    for code in role_codes:
        role_id = (await session.execute(select(Role.id).where(Role.code == code))).scalar_one()
        exists = (
            await session.execute(
                select(UserRole).where(UserRole.membership_id == membership.id, UserRole.role_id == role_id)
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                UserRole(
                    organization_id=org.id,
                    membership_id=membership.id,
                    role_id=role_id,
                    granted_at=datetime.now(UTC),
                )
            )
    session.add(
        AuditLog(
            organization_id=org.id,
            action="membership.granted",
            entity_type="user",
            entity_id=str(user.id),
            after={"roles": role_codes},
        )
    )
    return user


def _maker() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(get_settings().migration_database_url)
    return async_sessionmaker(engine, expire_on_commit=False)


async def cmd_org_create(args: argparse.Namespace) -> None:
    password = args.admin_password or secrets.token_urlsafe(12)
    maker = _maker()
    async with maker() as session, session.begin():
        org = await create_org(session, slug=args.slug, name=args.name, locale=args.locale)
        await add_member(
            session,
            org,
            email=args.admin_email,
            full_name=args.admin_name,
            role_codes=["admin"],
            password=password,
            must_change_password=args.admin_password is None,
        )
    print(f"Đã tạo tổ chức '{args.slug}' (id: {org.id}).")
    if args.admin_password is None:
        print(f"Mật khẩu tạm của {args.admin_email}: {password} (bắt buộc đổi ở lần đăng nhập đầu)")


async def cmd_seed_dev(_: argparse.Namespace) -> None:
    if get_settings().environment != "local":
        raise SystemExit("seed-dev chỉ chạy ở môi trường local")
    maker = _maker()
    async with maker() as session, session.begin():
        for slug, name in SEED_ORGS.items():
            org = await create_org(session, slug=slug, name=name)
            for role in ALL_ROLES:
                await add_member(
                    session,
                    org,
                    email=f"{role}@{slug}.test",
                    full_name=f"{role} ({slug})",
                    role_codes=[role],
                    password=DEV_PASSWORD,
                    must_change_password=False,
                )
        platform = await create_org(session, slug="platform", name="Platform")
        await add_member(
            session,
            platform,
            email="platform-admin@talenthub.test",
            full_name="Platform Admin",
            role_codes=["platform_admin"],
            password=DEV_PASSWORD,
            must_change_password=False,
        )
    print(f"Đã seed dữ liệu dev. Tài khoản dạng <vai_trò>@<tổ_chức>.test, mật khẩu: {DEV_PASSWORD}")


async def cmd_seed_demo(args: argparse.Namespace) -> None:
    from src.demo.seed import seed_demo

    if get_settings().environment != "local":
        raise SystemExit("seed-demo chỉ chạy ở môi trường local")
    maker = _maker()
    async with maker() as session, session.begin():
        org = (await session.execute(select(Organization).where(Organization.slug == args.org))).scalar_one_or_none()
        if org is None:
            raise SystemExit(f"Không có tổ chức '{args.org}'. Chạy seed-dev trước.")
        await set_org_context(session, org.id)
        summary = await seed_demo(session, org, current_applications=args.current)
    print("Đã nạp dữ liệu minh hoạ (TỔNG HỢP, không phải dữ liệu thật):")
    for c in summary["cohorts"]:
        print(f"  {c['code']}: {c['applicants']} hồ sơ, nhận {c['admitted']}, đạt yêu cầu {c['qualified']}")
    print(f"  Đợt đang tuyển: {summary['current']['applications']} hồ sơ đã nộp (id {summary['current']['intake_id']})")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(prog="src.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    org = sub.add_parser("org").add_subparsers(dest="org_cmd", required=True)
    create = org.add_parser("create")
    create.add_argument("--slug", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--locale", default="vi")
    create.add_argument("--admin-email", required=True)
    create.add_argument("--admin-name", default="Quản trị viên")
    create.add_argument("--admin-password", default=None)
    create.set_defaults(func=cmd_org_create)

    sub.add_parser("seed-dev").set_defaults(func=cmd_seed_dev)
    demo = sub.add_parser("seed-demo")
    demo.add_argument("--org", default="northwind")
    demo.add_argument("--current", type=int, default=600)
    demo.set_defaults(func=cmd_seed_demo)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
