"""Phản hồi cho phân tích: phễu, giám sát công bằng, Rubric Lab."""

import uuid

from src.schemas.responses.common import Out


class FunnelIntake(Out):
    id: uuid.UUID
    name: str
    quota: int
    status: str


class FunnelStage(Out):
    key: str
    label: str
    count: int


class FunnelOut(Out):
    intake: FunnelIntake
    by_status: dict[str, int]
    stages: list[FunnelStage]
    decisions: dict[str, int]
    median_days_to_decision: float | None
    quota_fill: float | None


class GroupRates(Out):
    rates: dict[str, float]
    sizes: dict[str, int]
    impact_ratio: float | None


class FairnessIntake(Out):
    id: uuid.UUID
    name: str


class FairnessOut(Out):
    intake: FairnessIntake
    stages: dict[str, dict[str, GroupRates]]
    warnings: list[str]
    note: str


class LabCriterionDef(Out):
    id: str
    name: str
    weight: float


class LabCriterionStat(Out):
    criterion: str
    coef: float
    ci90: list[float]
    significant: bool
    auc: float | None
    mean_if_qualified: float
    mean_if_not: float


class LabAnalysis(Out):
    n: int
    events: int
    qualified_rate: float | None = None
    criteria: list[LabCriterionStat]
    model_auc: float | None
    warnings: list[str]
    reliable: bool


class ObservedRate(Out):
    known: int
    of: int
    qualified_rate: float | None


class LabSimulation(Out):
    pool: int
    selected: int
    overlap_old_new: float
    changed_in: int
    overlap_actual_old: float
    observed_old: ObservedRate
    observed_new: ObservedRate
    fairness_old: dict[str, GroupRates]
    fairness_new: dict[str, GroupRates]
    newly_selected_ids: list[str]
    dropped_ids: list[str]
    model_expected_old: float | None = None
    model_expected_new: float | None = None
    model_note: str | None = None


class LabOut(Out):
    criteria: list[LabCriterionDef]
    analysis: LabAnalysis
    pool: int
    admitted: int
    old_weights: dict[str, float]
    simulation: LabSimulation | None = None
    new_weights: dict[str, float] | None = None


class LabIntakeCriterion(Out):
    id: str
    name: str


class LabIntakeOut(Out):
    id: uuid.UUID
    name: str
    status: str
    admitted: int
    with_outcome: int
    criteria: list[LabIntakeCriterion]


class QualityCohort(Out):
    id: uuid.UUID
    code: str
    name: str
    status: str
    classes: int


class QualitySummary(Out):
    learners: int
    active: int
    qualified: int
    not_qualified: int
    withdrawn: int
    qualified_rate: float | None
    coverage: float | None
    attainment: float | None


class QualityTrackCell(Out):
    track_id: uuid.UUID
    track: str
    targeted: int
    assessed: int
    met: int
    attainment: float | None


class QualityCompetency(Out):
    id: uuid.UUID
    code: str
    name: str
    targeted: int
    assessed: int
    met: int
    attainment: float | None
    coverage: float | None
    avg_gap: float | None
    previous: float | None
    by_track: list[QualityTrackCell]


class QualityTrack(Out):
    track_id: uuid.UUID
    track: str
    learners: int
    qualified: int
    not_qualified: int
    active: int
    qualified_rate: float | None


class QualityAlertItem(Out):
    label: str
    ref_type: str
    ref_id: str


class QualityAlert(Out):
    code: str
    severity: str
    title: str
    detail: str
    count: int
    items: list[QualityAlertItem]


class QualityRecommendation(Out):
    priority: str
    area: str
    title: str
    rationale: str
    actions: list[str]


class QualityOut(Out):
    cohort: QualityCohort
    previous_cohort: str | None
    summary: QualitySummary
    competencies: list[QualityCompetency]
    tracks: list[QualityTrack]
    alerts: list[QualityAlert]
    recommendations: list[QualityRecommendation]
    thresholds: dict[str, float]
