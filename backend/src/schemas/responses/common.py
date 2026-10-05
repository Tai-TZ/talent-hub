"""Nền chung cho mô hình phản hồi.

Mô hình phản hồi KHÔNG áp validator đầu vào (đường dẫn, độ dài...): dữ liệu đã lưu hợp lệ theo quy tắc lúc ghi,
và một số trường được che có chủ đích (ví dụ "(ẩn)" khi chấm mù). Mục đích của chúng là: (1) hợp đồng API rõ ràng
cho FE sinh kiểu, (2) lọc bỏ trường không khai báo để không lộ dữ liệu ngoài ý muốn.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class Out(BaseModel):
    model_config = ConfigDict(extra="ignore")


class RoundOut(Out):
    key: str
    label: str
    type: str = "review"


class FlagOut(Out):
    source: str
    rule: str | None = None
    label: str
    severity: str = "warning"


class IdName(Out):
    id: uuid.UUID
    name: str


class MovedOut(Out):
    moved: int


class StampOut(Out):
    at: datetime


class InvitationPreviewOut(Out):
    organization: str
    email: str
    kind: str
    has_password: bool
