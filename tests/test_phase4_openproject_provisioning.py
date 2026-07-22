from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVISIONER = ROOT / "infra" / "openproject" / "provision" / "ensure_agent_bot_token_webhook.rb"
COMPOSE = ROOT / "docker-compose.yml"
INFRA_README = ROOT / "infra" / "README.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_openproject_provisioner_discovers_required_catalog_resources():
    provisioner = read(PROVISIONER)

    for function_name in [
        "discover_work_package_types!",
        "discover_statuses!",
        "discover_priorities!",
        "ensure_custom_fields!",
    ]:
        assert f"def {function_name}" in provisioner

    for env_name in [
        "OP_REQUIRED_WORK_PACKAGE_TYPES",
        "OP_SEMANTIC_STATUS_NAMES",
        "OP_REQUIRED_PRIORITIES",
        "OP_ENSURE_AGENT_CUSTOM_FIELDS",
    ]:
        assert env_name in provisioner

    for field_name in [
        "Agent Entity ID",
        "Agent Execution Status",
        "Verification Status",
        "Repository Key",
        "Requirement Keys",
    ]:
        assert field_name in provisioner

    assert 'env_bool("OP_ENSURE_AGENT_CUSTOM_FIELDS", false)' in provisioner


def test_openproject_provisioner_writes_non_secret_discovery_report():
    provisioner = read(PROVISIONER)

    for report_key in [
        '"bot_user"',
        '"api_token_file"',
        '"work_package_types"',
        '"statuses"',
        '"priorities"',
        '"custom_fields"',
        '"webhook"',
        '"starter_project"',
        '"project_modules"',
        '"project_role"',
        '"sample_binding"',
        '"warnings"',
    ]:
        assert report_key in provisioner

    assert "OP_PROVISIONING_OUTPUT_FILE" in provisioner
    assert "openproject_provisioning.json" in provisioner
    assert "JSON.pretty_generate(payload)" in provisioner
    assert '"api_token" =>' not in provisioner


def test_openproject_provisioner_ensures_project_binding_and_permissions():
    provisioner = read(PROVISIONER)

    for function_name in [
        "ensure_project_modules!",
        "ensure_project_role_for_bot!",
        "ensure_sample_project_binding!",
    ]:
        assert f"def {function_name}" in provisioner

    for env_name in [
        "OP_REQUIRED_PROJECT_MODULES",
        "OP_AGENT_ROLE_NAME",
        "OP_AGENT_ROLE_PERMISSIONS",
        "OP_STARTER_REPOSITORY_KEY",
        "OP_STARTER_REPOSITORY_PATH",
    ]:
        assert env_name in provisioner

    assert "Agent repository binding:" in provisioner
    assert provisioner.count("def ensure_starter_project!") == 1
    assert "# def ensure_starter_project!" not in provisioner


def test_compose_wires_openproject_provisioning_defaults():
    compose = read(COMPOSE)

    for env_name in [
        "OP_PROVISIONING_OUTPUT_FILE",
        "OP_REQUIRED_WORK_PACKAGE_TYPES",
        "OP_SEMANTIC_STATUS_NAMES",
        "OP_REQUIRED_PRIORITIES",
        "OP_REQUIRED_PROJECT_MODULES",
        "OP_ENSURE_AGENT_CUSTOM_FIELDS",
        "OP_AGENT_ROLE_NAME",
        "OP_AGENT_ROLE_PERMISSIONS",
        "OP_STARTER_REPOSITORY_KEY",
        "OP_STARTER_REPOSITORY_PATH",
    ]:
        assert f"{env_name}:" in compose

    assert "OPENPROJECT_PROVISIONING_REPORT_FILE=/agent-secrets/openproject_provisioning.json" in compose


def test_infra_readme_documents_provisioning_report_and_custom_field_policy():
    readme = read(INFRA_README)

    assert "/agent-secrets/openproject_provisioning.json" in readme
    assert "discovered OpenProject IDs" in readme
    assert "OP_ENSURE_AGENT_CUSTOM_FIELDS=false" in readme
    assert "custom fields are discovered and reported but not created" in readme
