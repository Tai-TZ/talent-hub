import re
import uuid
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SLUG = re.compile(r"^[a-z][a-z0-9_]{1,39}$")

CriterionKind = Literal[
    "education",
    "programming",
    "projects",
    "ai_ml",
    "data",
    "experience",
    "motivation",
    "problem_solving",
    "communication",
    "custom",
]


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=600)] = ""
    weight: float = Field(gt=0, le=10)
    max: float = Field(default=5, gt=0, le=100)
    kind: CriterionKind = "custom"

    @model_validator(mode="after")
    def _slug(self) -> "Criterion":
        if not SLUG.match(self.id):
            raise ValueError("id tiêu chí chỉ gồm chữ thường, số và dấu gạch dưới, bắt đầu bằng chữ")
        return self


class RoundIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: Annotated[str, Field(min_length=1, max_length=80)]
    type: Literal["review", "assessment", "interview"] = "review"

    @model_validator(mode="after")
    def _slug(self) -> "RoundIn":
        if not SLUG.match(self.key):
            raise ValueError("khoá vòng chỉ gồm chữ thường, số và dấu gạch dưới")
        return self


class EligibilityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: Annotated[str, Field(min_length=1, max_length=200)]
    type: Literal["education_status_in", "min_skills", "min_projects", "min_essay_chars"]
    values: list[str] = Field(default_factory=list, max_length=10)
    value: int | None = Field(default=None, ge=0, le=100000)


class TriageThresholds(BaseModel):
    """Ngưỡng sàng lọc AI (điểm 0–100, độ tin cậy 0–1). Thiếu khoá nào thì dùng mặc định của động cơ chấm."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    invite: float | None = Field(default=None, ge=0, le=100)
    decline: float | None = Field(default=None, ge=0, le=100)
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    margin: float | None = Field(default=None, ge=0, le=50)

    @model_validator(mode="after")
    def _ordered(self) -> "TriageThresholds":
        if self.invite is not None and self.decline is not None and self.decline >= self.invite:
            raise ValueError("Ngưỡng 'khả năng loại' phải thấp hơn ngưỡng 'nên mời'")
        return self


class TriageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thresholds: TriageThresholds = Field(default_factory=TriageThresholds)

    def stored(self) -> dict[str, Any]:
        """Dạng lưu JSONB: bỏ các ngưỡng không đặt để động cơ dùng mặc định."""
        return self.model_dump(exclude_none=True)


class IntakeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: uuid.UUID
    cohort_id: uuid.UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=4000)] = ""
    # Bắt buộc có múi giờ: so sánh với cột timestamptz của DB, giá trị "naive" sẽ gây TypeError (500).
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    quota: int = Field(gt=0, le=100000)
    rounds: Annotated[list[RoundIn], Field(min_length=1, max_length=6)]
    approval_mode: Literal["two_level"] = "two_level"
    ai_screening_enabled: bool = False
    blind_review: bool = True
    min_reviews: int = Field(default=1, ge=1, le=5)
    eligibility_rules: list[EligibilityRule] = Field(default_factory=list, max_length=20)
    triage_config: TriageConfig = Field(default_factory=TriageConfig)

    @model_validator(mode="after")
    def _check(self) -> "IntakeIn":
        if self.closes_at <= self.opens_at:
            raise ValueError("closes_at phải sau opens_at")
        keys = [r.key for r in self.rounds]
        if len(set(keys)) != len(keys):
            raise ValueError("Khoá vòng bị trùng")
        return self


class IntakePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    description: Annotated[str, Field(max_length=4000)] | None = None
    closes_at: AwareDatetime | None = None
    quota: int | None = Field(default=None, gt=0, le=100000)
    ai_screening_enabled: bool | None = None
    blind_review: bool | None = None
    min_reviews: int | None = Field(default=None, ge=1, le=5)
    eligibility_rules: list[EligibilityRule] | None = None
    triage_config: TriageConfig | None = None


class RubricIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: Annotated[list[Criterion], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def _unique(self) -> "RubricIn":
        ids = [c.id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("id tiêu chí bị trùng")
        return self
