from typing import Any


def should_agent_start(status_name: str | None, allowed_status_names: set[str]) -> bool:
    if not status_name:
        return False
    return status_name.strip().lower() in allowed_status_names


def run_coding_agent_placeholder(
    *,
    event: dict[str, Any],
    work_package: dict[str, Any],
    activities: dict[str, Any],
) -> str:
    """
    Replace this function with the real coding agent.

    Future implementation should:
    1. Sync OpenProject hierarchy/comments/decisions to Neo4j.
    2. Embed descriptions/comments/code context into Weaviate.
    3. Build task context from PM + code graph + vector DB.
    4. Create/checkout a git branch.
    5. Use LSP/tree-sitter/code graph retrieval.
    6. Implement.
    7. Run tests.
    8. Post result back to OpenProject.
    """
    wp_id = event.get("external_work_package_id")
    subject = work_package.get("subject")
    status = work_package.get("_links", {}).get("status", {}).get("title")
    comment_count = len(activities.get("_embedded", {}).get("elements", []))

    return (
        f"Agent placeholder executed for work package {wp_id}.\n\n"
        f"- Subject: {subject}\n"
        f"- Status: {status}\n"
        f"- Activity/comment count fetched: {comment_count}\n\n"
        "Replace run_coding_agent_placeholder() with the real coding-agent runner."
    )
