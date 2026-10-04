from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-dev-only-change-me"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"

    # Vai trò runtime: không superuser, không BYPASSRLS (xem docs/09-multi-tenancy.md).
    database_url: str = "postgresql+asyncpg://talenthub_app:app@localhost:5432/talenthub"
    # Vai trò chủ sở hữu bảng: chỉ cho migration và CLI vận hành nền tảng.
    migration_database_url: str = "postgresql+asyncpg://talenthub_owner:owner@localhost:5432/talenthub"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout_s: int = 10
    # Chặn truy vấn treo và transaction bỏ quên giữ khoá/kết nối.
    db_statement_timeout_ms: int = 15_000
    db_idle_in_tx_timeout_ms: int = 30_000

    redis_url: str | None = None

    jwt_secret: str = DEV_JWT_SECRET
    jwt_issuer: str = "talenthub"
    jwt_audience: str = "talenthub-api"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = False

    # Xác định tổ chức: tên miền con `<slug>.<base_domain>`; header chỉ cho môi trường local.
    base_domain: str = "localhost"
    allow_org_header: bool = True
    # BFF (Next.js) gửi X-Organization kèm X-Internal-Auth = secret này; backend chỉ tin header khi khớp.
    internal_proxy_secret: str | None = None
    allowed_hosts: list[str] = ["*"]
    allowed_origins: list[str] = ["http://localhost:3000"]

    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_limit_per_minute: int = 30
    # Argon2 tốn ~64 MiB mỗi lần băm: giới hạn số lần băm chạy đồng thời để không cạn bộ nhớ.
    password_hash_concurrency: int = 4

    max_body_bytes: int = 1_048_576

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @model_validator(mode="after")
    def _reject_unsafe_production(self) -> "Settings":
        if self.is_local:
            return self
        problems: list[str] = []
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET phải được đặt và dài tối thiểu 32 ký tự")
        if self.allow_org_header:
            problems.append("ALLOW_ORG_HEADER phải tắt")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE phải bật")
        if not self.redis_url:
            problems.append("REDIS_URL phải được đặt (giới hạn tốc độ dùng chung giữa các tiến trình)")
        if "*" in self.allowed_hosts:
            problems.append("ALLOWED_HOSTS không được chứa '*'")
        if "*" in self.allowed_origins:
            problems.append("ALLOWED_ORIGINS không được chứa '*'")
        if problems:
            raise ValueError("Cấu hình không an toàn khi ENVIRONMENT != local: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
