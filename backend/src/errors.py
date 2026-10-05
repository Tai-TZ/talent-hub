"""Lỗi nghiệp vụ. Tầng services ném các lỗi này; tầng api ánh xạ sang mã HTTP (src/api/errors.py)."""


class DomainError(Exception):
    """Gốc của mọi lỗi nghiệp vụ; `message` là nội dung an toàn để trả cho người dùng."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidCredentialsError(DomainError):
    pass


class InvalidRefreshTokenError(DomainError):
    pass


class PasswordPolicyError(DomainError):
    pass


class RateLimitedError(DomainError):
    def __init__(self, retry_after_s: int) -> None:
        super().__init__("Quá nhiều yêu cầu, vui lòng thử lại sau")
        self.retry_after_s = retry_after_s


class NotFoundError(DomainError):
    pass


class PermissionDeniedError(DomainError):
    pass


class ConflictError(DomainError):
    """Trạng thái đã đổi bởi người khác (khoá lạc quan) hoặc vi phạm ràng buộc duy nhất."""


class InvalidTransitionError(DomainError):
    """Chuyển trạng thái không nằm trong bảng chuyển hợp lệ."""


class ValidationFailedError(DomainError):
    """Dữ liệu không hợp lệ về mặt nghiệp vụ; `fields` chỉ ra từng trường lỗi để giao diện hiển thị."""

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.fields = fields or {}
