/** Tên gọn cho các mô hình phản hồi của BE (sinh tự động trong api-types.ts bằng `make api-types`). */
import type { components } from "./api-types";

type S = components["schemas"];

export type IntakeT = S["IntakeOut"];
export type ProgramT = S["ProgramOut"];
export type ApplicationSummary = S["ApplicationSummaryOut"];
export type ApplicationView = S["ApplicationViewOut"];
export type TimelineEvent = S["TimelineEventOut"];
export type NotificationList = S["NotificationListOut"];

export type QueuePage = S["QueuePageOut"];
export type QueueItem = S["QueueItemOut"];
export type StaffApplication = S["StaffApplicationOut"];
export type Rubric = S["RubricOut"];
export type Criterion = S["CriterionOut"];
export type AiAssessment = S["AiAssessmentOut"];
export type AiLocked = S["AiLockedOut"];
export type ApprovalRow = S["ApprovalRowOut"];
export type TriageBoard = S["TriageBoardOut"];
export type TriageItem = S["TriageItemOut"];
export type Job = S["JobOut"];

export type CohortOverview = S["CohortOverviewOut"];
export type EnrollmentPage = S["EnrollmentPageOut"];
export type Enrollment = S["EnrollmentOut"];
export type Track = S["TrackOut"];
export type Partner = S["PartnerOut"];
export type Competencies = S["CompetenciesOut"];
export type MentorLearner = S["MentorLearnerOut"];
export type QualificationRow = S["QualificationRowOut"];
export type StipendSummary = S["StipendSummaryOut"];
export type ComposerRun = S["ComposerRunOut"];
export type ComposerRunDetail = S["ComposerRunDetailOut"];

export type Funnel = S["FunnelOut"];
export type Fairness = S["FairnessOut"];
export type Lab = S["LabOut"];

export type AdminOverview = S["OverviewOut"];
export type AccountPage = S["AccountPageOut"];
export type Account = S["AccountOut"];
export type AccountCreated = S["AccountCreatedOut"];
export type ImportResult = S["ImportResultOut"];
export type DocumentPage = S["DocumentPageOut"];
export type DocumentDetail = S["DocumentDetailOut"];
export type SearchHit = S["SearchHitOut"];
export type CostSummary = S["CostSummaryOut"];
export type CostEntryPage = S["CostEntryPageOut"];
export type AiUsageRow = S["AiUsageRowOut"];
export type SettingsT = S["SettingsOut"];
export type InvitationPreview = S["InvitationPreviewOut"];
