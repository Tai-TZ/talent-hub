"""Cấu trúc hồ sơ ứng viên. Tách `profile` (nhận dạng, nhạy cảm) khỏi `content` (năng lực).

Chỉ `content` được dùng làm đầu vào cho AI chấm sơ bộ; `profile` không bao giờ đi vào prompt
(tránh thiên lệch theo giới tính, nơi ở, ngày sinh).
"""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_URL = re.compile(r"^https?://[^\s<>\"']{3,300}$", re.IGNORECASE)


def _clean(value: str) -> str:
    """Bỏ ký tự điều khiển và khoảng trắng thừa; giữ xuống dòng cho các ô văn bản dài."""
    return _CONTROL.sub("", value).strip()


Text = Annotated[str, AfterValidator(_clean)]


def _url(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    value = _clean(value)
    if not _URL.match(value):
        raise ValueError("Đường dẫn phải bắt đầu bằng http:// hoặc https://")
    return value


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Profile(_Strict):
    full_name: Annotated[Text, Field(min_length=1, max_length=120)]
    phone: Annotated[Text, Field(max_length=20, pattern=r"^[0-9+()\-. ]{8,20}$")] | None = None
    date_of_birth: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    # Tự khai, tuỳ chọn; chỉ dùng trong thống kê công bằng gộp nhóm, không dùng để chấm.
    gender: Literal["female", "male", "other", "undisclosed"] | None = None
    city: Annotated[Text, Field(max_length=80)] | None = None


class Education(_Strict):
    school: Annotated[Text, Field(min_length=1, max_length=160)]
    degree: Annotated[Text, Field(max_length=120)] = ""
    major: Annotated[Text, Field(max_length=120)] = ""
    status: Literal["student", "final_year", "graduated", "other"] = "student"
    year: int | None = Field(default=None, ge=1990, le=2100)
    gpa: float | None = Field(default=None, ge=0, le=10)


class Experience(_Strict):
    org: Annotated[Text, Field(min_length=1, max_length=160)]
    role: Annotated[Text, Field(max_length=120)] = ""
    years: float = Field(default=0, ge=0, le=50)
    description: Annotated[Text, Field(max_length=1500)] = ""


class Project(_Strict):
    title: Annotated[Text, Field(min_length=1, max_length=160)]
    description: Annotated[Text, Field(max_length=2000)] = ""
    link: str | None = None
    tech: list[Annotated[Text, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=15)

    _check_link = field_validator("link")(_url)


class Essays(_Strict):
    motivation: Annotated[Text, Field(max_length=4000)] = ""
    problem_solving: Annotated[Text, Field(max_length=4000)] = ""


class Links(_Strict):
    github: str | None = None
    linkedin: str | None = None
    portfolio: str | None = None

    _check = field_validator("github", "linkedin", "portfolio")(_url)


class Preferences(_Strict):
    """Nguyện vọng nhánh của ứng viên (theo thứ tự ưu tiên); không dùng để chấm điểm."""

    tracks: list[Annotated[Text, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=3)


class Content(_Strict):
    education: list[Education] = Field(default_factory=list, max_length=10)
    experience: list[Experience] = Field(default_factory=list, max_length=15)
    projects: list[Project] = Field(default_factory=list, max_length=15)
    skills: list[Annotated[Text, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=40)
    essays: Essays = Field(default_factory=Essays)
    links: Links = Field(default_factory=Links)
    cv_text: Annotated[Text, Field(max_length=20000)] = ""
    preferences: Preferences = Field(default_factory=Preferences)


MIN_ESSAY_CHARS = 200


def submission_errors(profile: Profile | None, content: Content | None) -> dict[str, str]:
    """Các trường còn thiếu để được nộp. Trả về {đường_dẫn_trường: thông_báo}."""
    errors: dict[str, str] = {}
    if profile is None or not profile.full_name:
        errors["profile.full_name"] = "Vui lòng nhập họ tên"
    if profile is None or not profile.phone:
        errors["profile.phone"] = "Vui lòng nhập số điện thoại"
    if content is None or not content.education:
        errors["content.education"] = "Thêm ít nhất một thông tin học vấn"
    if content is None or not content.skills:
        errors["content.skills"] = "Thêm ít nhất một kỹ năng"
    motivation = content.essays.motivation if content else ""
    if len(motivation) < MIN_ESSAY_CHARS:
        errors["content.essays.motivation"] = f"Hãy viết ít nhất {MIN_ESSAY_CHARS} ký tự về động lực của bạn"
    return errors
