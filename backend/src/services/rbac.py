"""Vai trò → permission. Nguồn sự thật: bảng permission trong docs/06-api-spec.md."""

PERMISSIONS: dict[str, frozenset[str]] = {
    "applicant": frozenset(
        {
            "application.create",
            "application.read.own",
            "application.write.own",
            "intake.read",
            "assistant.use",
        }
    ),
    "reviewer": frozenset(
        {
            "application.read",
            "application.review",
            "decision.propose",
            "intake.read",
            "analytics.read",
            "assistant.use",
        }
    ),
    "approver": frozenset(
        {
            "application.read",
            "decision.approve",
            "triage.read",
            "intake.read",
            "analytics.read",
            "assistant.use",
        }
    ),
    "cohort_manager": frozenset(
        {
            "application.read",
            "pii.read",
            "cohort.read",
            "cohort.manage",
            "intake.read",
            "analytics.read",
            "assistant.use",
        }
    ),
    "training_manager": frozenset(
        {
            "training.read",
            "training.manage",
            "cohort.read",
            "mentor.assess",
            "intake.read",
            "analytics.read",
            "export.read",
            "assistant.use",
        }
    ),
    "mentor": frozenset({"mentor.assess", "assistant.use"}),
    "admin": frozenset(
        {
            "application.read",
            "application.assign",
            "intake.read",
            "intake.manage",
            "user.manage",
            "integration.manage",
            "kb.manage",
            "audit.read",
            "analytics.read",
            "export.read",
            "training.read",
            "cohort.read",
            "triage.read",
            "triage.run",
            "pii.read",
            "cost.read",
            "cost.manage",
            "job.read",
            "assistant.use",
        }
    ),
    "platform_admin": frozenset({"platform.manage"}),
}


def permissions_for(role_codes: set[str] | frozenset[str]) -> frozenset[str]:
    result: set[str] = set()
    for code in role_codes:
        result |= PERMISSIONS.get(code, frozenset())
    return frozenset(result)
