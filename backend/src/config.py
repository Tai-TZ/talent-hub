from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-change-me-dev-only-change-me"  # noqa: S105
# Tên quen thuộc được chấp nhận cho LLM_PROVIDER, đều đi qua lớp tương thích OpenAI.
LLM_PROVIDER_ALIASES = frozenset({"openai", "openrouter", "gemini", "openai-compatible"})


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
    max_upload_bytes: int = 22_000_000  # 15 MB tệp sau khi mã hoá base64

    # Email: console (ghi log) | smtp | none. Local dùng Mailpit tại localhost:1025 khi chọn smtp.
    email_backend: str = "console"
    email_from: str = "Talent Hub <no-reply@talenthub.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_starttls: bool = False
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Gốc URL của giao diện, dùng để dựng link trong email (lời mời, đặt lại mật khẩu).
    public_base_url: str = "http://localhost:3000"

    # Đăng nhập Microsoft (Entra ID, OIDC code flow + PKCE). Tắt khi chưa có client_id.
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    # "common" nhận cả tài khoản cơ quan và cá nhân; có thể đặt GUID tenant của trường để giới hạn.
    microsoft_tenant: str = "common"
    microsoft_authority: str = "https://login.microsoftonline.com"
    # Mặc định đi qua giao diện (BFF) để cookie cùng origin: <public_base_url>/api/v1/auth/microsoft/callback
    microsoft_redirect_uri: str | None = None

    # AI: "heuristic" chạy offline không cần khoá; "llm" dùng LLM đã cấu hình và tự lùi về luật khi dịch vụ lỗi.
    ai_engine: str = "heuristic"
    anthropic_api_key: str | None = None
    ai_scoring_model: str = "claude-opus-5-5"
    ai_concurrency: int = 6
    # Số tiến trình con chấm song song bằng động cơ luật khi đợt lớn (chạy CPU, không chặn API). 0 = chấm ngay trong
    # tiến trình API.
    triage_workers: int = 4
    # Trợ lý hỏi đáp được gọi nhiều hơn chấm hồ sơ: dùng mô hình nhỏ, rẻ.
    assistant_model: str = "claude-haiku-4-5-20251001"

    # Nhà cung cấp LLM: "auto" (mặc định) chọn openai_compatible khi có LLM_API_KEY, rồi anthropic khi có
    # ANTHROPIC_API_KEY, không có khoá nào thì chạy offline. Cài đặt của tổ chức (ai_engine/assistant_engine) vẫn
    # quyết định offline hay LLM; các biến dưới đây chỉ quyết định dùng LLM NÀO.
    llm_provider: str = "auto"
    # Dịch vụ tương thích OpenAI Chat Completions (OpenRouter, OpenAI, Gemini...). Mặc định là OpenRouter.
    llm_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    # Tên mô hình theo cách gọi của nhà cung cấp (OpenRouter có tiền tố "hãng/"). Đổi được qua biến môi trường;
    # mô hình phải hỗ trợ đầu ra JSON theo schema (structured output).
    llm_scoring_model: str = "google/gemini-2.5-flash"
    llm_assistant_model: str = "google/gemini-2.5-flash-lite"
    # "json_schema": ép đầu ra theo schema (strict). "json_object": cho mô hình không hỗ trợ schema; schema được đưa
    # vào prompt và đầu ra vẫn được kiểm chứng bằng Pydantic.
    llm_json_mode: str = "json_schema"
    # Giá tuỳ chỉnh (USD mỗi triệu token) cho LLM_SCORING_MODEL/LLM_ASSISTANT_MODEL, ưu tiên hơn bảng giá có sẵn.
    # Cần đặt cả hai để có hiệu lực; dùng khi mô hình chưa có trong src/ai/pricing.py.
    llm_price_input_per_mtok: float | None = None
    llm_price_output_per_mtok: float | None = None

    @field_validator("llm_provider", mode="before")
    @classmethod
    def _normalize_llm_provider(cls, value: object) -> str:
        name = str(value or "auto").strip().lower() or "auto"
        if name in LLM_PROVIDER_ALIASES:
            return "openai_compatible"
        if name not in {"auto", "openai_compatible", "anthropic"}:
            raise ValueError("LLM_PROVIDER phải là auto, openai_compatible hoặc anthropic")
        return name

    @field_validator("llm_json_mode", mode="before")
    @classmethod
    def _normalize_json_mode(cls, value: object) -> str:
        mode = str(value or "json_schema").strip().lower() or "json_schema"
        if mode not in {"json_schema", "json_object"}:
            raise ValueError("LLM_JSON_MODE phải là json_schema hoặc json_object")
        return mode

    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    @property
    def microsoft_enabled(self) -> bool:
        return bool(self.microsoft_client_id and self.microsoft_client_secret)

    @property
    def microsoft_callback_url(self) -> str:
        return self.microsoft_redirect_uri or f"{self.public_base_url.rstrip('/')}/api/v1/auth/microsoft/callback"

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
