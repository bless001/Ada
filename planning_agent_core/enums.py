from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    AWAITING_REVIEW = "awaiting_review"
    ACTIVE = "active"
    ARCHIVED = "archived"
    FAILED = "failed"


class PlanningSessionStatus(StrEnum):
    INTAKE = "intake"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY_FOR_PLANNING = "ready_for_planning"
    PLAN_DRAFTED = "plan_drafted"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    FAILED = "failed"


class InputMode(StrEnum):
    TEXT = "text"
    DOCUMENT = "document"
    OPENPROJECT = "openproject"
    REPOSITORY = "repository"


class PlanVersionStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class PlanNodeKind(StrEnum):
    VISION = "vision"
    CAPABILITY = "capability"
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
