from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from planning_agent_core.adapters.openproject import OpenProjectClient
from planning_agent_core.agent_platform.adapters.openproject import (
    ManagedWorkPackageGateway,
)
from planning_agent_core.agent_platform.agents.coding import (
    CodingAgentRequest,
    CodingAgentResult,
)
from planning_agent_core.agent_platform.agents.verification import (
    VerificationAgentResult,
    VerificationVerdict,
)
from planning_agent_core.agent_platform.config import (
    AgentPlatformConfig,
    load_agent_platform_config,
)
from planning_agent_core.agent_platform.orchestration import (
    AgentExecutionRequest,
    AgentFlowStatus,
)
from planning_agent_core.application.openproject_mapping import (
    OpenProjectResourceCatalog,
    OpenProjectSemanticMapper,
)
from planning_agent_core.domain.coding import (
    CodingAttemptRequest,
    FileChange,
    QualityCommand,
)
from planning_agent_core.domain.enums import (
    PlanNodeKind,
    PlanVersionStatus,
    RepositoryAccessMode,
)
from planning_agent_core.domain.repositories import RepositoryBinding
from planning_agent_core.models import (
    ExternalArtifact,
    OpenProjectOutboundOperation,
    PlanNode,
    PlanNodeIdentity,
    PlanVersion,
    Project,
)
from planning_agent_core.persistence.openproject_artifacts import (
    SqlAlchemyOpenProjectArtifactStore,
)
from planning_agent_core.persistence.openproject_outbox import (
    SqlAlchemyOpenProjectOutboundStore,
)
from planning_agent_core.persistence.openproject_reconciliation import (
    SqlAlchemyOpenProjectReconciliationStore,
)
from planning_agent_core.persistence.repository_bindings import (
    SqlAlchemyRepositoryBindingStore,
)
from planning_agent_core.services.agent_platform_composition import (
    create_agent_platform_service_for_db,
)


_ENABLED_ENV = "PHASE9_E2E_ENABLED"
_DATABASE_URL_ENV = "PHASE9_E2E_DATABASE_URL"
_OPENPROJECT_URL_ENV = "PHASE9_OPENPROJECT_BASE_URL"
_OPENPROJECT_TOKEN_ENV = "PHASE9_OPENPROJECT_API_TOKEN"
_OPENPROJECT_TOKEN_FILE_ENV = "PHASE9_OPENPROJECT_API_TOKEN_FILE"
_OPENPROJECT_PROJECT_ENV = "PHASE9_OPENPROJECT_PROJECT_ID"
_VERIFIED_STATUS_ENV = "PHASE9_OPENPROJECT_VERIFIED_STATUS_NAME"


@dataclass(frozen=True)
class Phase9E2EConfig:
    database_url: str = field(repr=False)
    openproject_base_url: str
    openproject_api_token: str = field(repr=False)
    openproject_project_id: str
    configured_verified_status: str | None = None


@pytest.fixture(scope="module")
def phase9_e2e_config() -> Phase9E2EConfig:
    if os.getenv(_ENABLED_ENV, "").lower() not in {"1", "true", "yes"}:
        pytest.skip(f"Set {_ENABLED_ENV}=1 to run the Phase 9 OpenProject E2E test")

    database_url = _required_env(_DATABASE_URL_ENV)
    base_url = _required_env(_OPENPROJECT_URL_ENV)
    project_id = _required_env(_OPENPROJECT_PROJECT_ENV)
    token = os.getenv(_OPENPROJECT_TOKEN_ENV, "").strip()
    token_file = os.getenv(_OPENPROJECT_TOKEN_FILE_ENV, "").strip()
    if not token and token_file:
        token = Path(token_file).read_text(encoding="utf-8").strip()
    if not token:
        pytest.fail(
            f"Set {_OPENPROJECT_TOKEN_ENV} or {_OPENPROJECT_TOKEN_FILE_ENV} "
            "to a test bot token"
        )

    _run_migrations(database_url)
    return Phase9E2EConfig(
        database_url=database_url,
        openproject_base_url=base_url,
        openproject_api_token=token,
        openproject_project_id=project_id,
        configured_verified_status=(
            os.getenv(_VERIFIED_STATUS_ENV, "").strip() or None
        ),
    )


@pytest.fixture
def isolated_sample_project(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[2] / "sample_project"
    target = tmp_path / "sample_project"
    shutil.copytree(source, target)
    services = target / "services"
    services.mkdir()
    (services / "__init__.py").write_text("", encoding="utf-8")
    (services / "payment.py").write_text(
        "\n".join(
            [
                "class PaymentService:",
                "    def charge(self, amount):",
                "        return amount",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target / "test_main.py").write_text(
        "def test_baseline_fixture():\n    assert True\n",
        encoding="utf-8",
    )
    _git(target, "init")
    _git(target, "add", ".")
    _git(
        target,
        "-c",
        "user.name=Phase 9 E2E",
        "-c",
        "user.email=phase9-e2e@example.test",
        "commit",
        "-m",
        "Initialize sample project fixture",
    )
    return target


@pytest.mark.asyncio
async def test_sample_project_coding_verification_updates_openproject(
    phase9_e2e_config: Phase9E2EConfig,
    isolated_sample_project: Path,
):
    engine = create_async_engine(phase9_e2e_config.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    run_key = uuid4().hex

    try:
        async with session_factory() as session:
            project, version, identity = await _persist_approved_task(
                session,
                run_key=run_key,
            )
            await SqlAlchemyRepositoryBindingStore(session).upsert_binding(
                project_id=project.id,
                binding=RepositoryBinding(
                    repository_key="sample-project",
                    mount_path=str(isolated_sample_project),
                    access_mode=RepositoryAccessMode.READ_WRITE,
                    write_allowlist=("main.py", "test_main.py"),
                    command_allowlist=(Path(sys.executable).name,),
                ),
            )

            gateway = _work_package_gateway(
                session,
                phase9_e2e_config,
            )
            work_package_id, verified_status_name = await _create_work_package(
                session=session,
                config=phase9_e2e_config,
                gateway=gateway,
                project=project,
                identity=identity,
                run_key=run_key,
            )
            platform_config = _platform_config(verified_status_name)
            service = create_agent_platform_service_for_db(
                session,
                platform_config=platform_config,
                work_package_gateway=gateway,
            )
            coding_attempt = CodingAttemptRequest(
                task_key=identity.stable_key,
                repository_key="sample-project",
                file_changes=[
                    FileChange(
                        relative_path="main.py",
                        content=_implemented_main(),
                    ),
                    FileChange(
                        relative_path="test_main.py",
                        content=_implemented_tests(),
                    ),
                ],
                quality_commands=[
                    QualityCommand(
                        command=(
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "test_main.py",
                        ),
                        timeout_seconds=60,
                    )
                ],
            )
            execution = AgentExecutionRequest(
                workflow_id=f"phase9-e2e-{run_key}",
                agent_type="coding",
                request=CodingAgentRequest(
                    project_id=project.project_key,
                    task_id=identity.stable_key,
                    objective=(
                        "Add percentage discounts to sample_project checkout totals."
                    ),
                    approved=True,
                    coding_attempt=coding_attempt,
                    metadata={
                        "transition_context": {
                            "plan_version_id": str(version.id),
                        }
                    },
                ),
                config=platform_config.agents["coding"],
                correlation_id=f"phase9-e2e-{run_key}",
            )

            flow = await service.start_flow(execution, max_steps=3)

            assert flow.status == AgentFlowStatus.COMPLETED
            assert [step.agent_type for step in flow.steps] == [
                "coding",
                "verification",
            ]
            coding_result = CodingAgentResult.model_validate(
                flow.steps[0].result_payload
            )
            verification_result = VerificationAgentResult.model_validate(
                flow.steps[1].result_payload
            )
            assert coding_result.coding_result is not None
            assert coding_result.coding_result.succeeded is True
            assert coding_result.coding_result.changed_files == [
                "main.py",
                "test_main.py",
            ]
            assert coding_result.coding_result.command_results[0].exit_code == 0
            assert verification_result.verdict == VerificationVerdict.PASSED
            assert (
                verification_result.acceptance_coverage.mandatory_criteria_satisfied
                is True
            )
            assert verification_result.test_adequacy.test_command_count == 1

            client = _openproject_client(session, phase9_e2e_config)
            try:
                work_package = await client.get_work_package(work_package_id)
                activities = await client.list_work_package_activities(
                    work_package_id
                )
            finally:
                await client.close()

            assert (
                work_package["_links"]["status"]["title"]
                == verified_status_name
            )
            serialized_activities = json.dumps(activities)
            assert "Verification result" in serialized_activities
            assert "ada:openproject-idempotency" in serialized_activities

            operations = list(
                (
                    await session.scalars(
                        select(OpenProjectOutboundOperation).where(
                            OpenProjectOutboundOperation.project_id == project.id
                        )
                    )
                ).all()
            )
            assert len(operations) == 3
            assert {operation.status for operation in operations} == {"succeeded"}
            mapping = await session.scalar(
                select(ExternalArtifact).where(
                    ExternalArtifact.project_id == project.id,
                    ExternalArtifact.node_identity_id == identity.id,
                    ExternalArtifact.external_id == work_package_id,
                )
            )
            assert mapping is not None
    finally:
        await engine.dispose()


async def _persist_approved_task(session, *, run_key: str):
    project = Project(
        project_key=f"phase9-e2e-{run_key[:16]}",
        name="Phase 9 sample_project E2E",
    )
    session.add(project)
    await session.flush()
    version = PlanVersion(
        project_id=project.id,
        version_number=1,
        status=PlanVersionStatus.APPROVED.value,
        generated_from="phase9_e2e",
        plan_json={},
    )
    identity = PlanNodeIdentity(
        project_id=project.id,
        stable_key="task.sample-project-discount",
        kind=PlanNodeKind.TASK.value,
    )
    session.add_all([version, identity])
    await session.flush()
    node = PlanNode(
        project_id=project.id,
        plan_version_id=version.id,
        node_identity_id=identity.id,
        kind=PlanNodeKind.TASK.value,
        title="Add percentage discounts",
        objective="Apply percentage discounts to checkout totals.",
        node_json={
            "acceptance_criteria": [
                {
                    "key": "ac.sample-project-discount",
                    "statement": (
                        "Discount percentage is applied by calculate_total "
                        "and covered by pytest tests."
                    ),
                    "verification_method": "pytest",
                }
            ]
        },
    )
    session.add(node)
    await session.flush()
    identity.current_plan_node_id = node.id
    await session.commit()
    return project, version, identity


def _work_package_gateway(
    session,
    config: Phase9E2EConfig,
) -> ManagedWorkPackageGateway:
    artifact_store = SqlAlchemyOpenProjectArtifactStore(session)
    outbound_store = SqlAlchemyOpenProjectOutboundStore(session)
    reconciliation_store = SqlAlchemyOpenProjectReconciliationStore(session)
    return ManagedWorkPackageGateway(
        lambda: OpenProjectClient(
            artifact_store=artifact_store,
            outbound_store=outbound_store,
            reconciliation_store=reconciliation_store,
            base_url=config.openproject_base_url,
            api_key=config.openproject_api_token,
        )
    )


def _openproject_client(
    session,
    config: Phase9E2EConfig,
) -> OpenProjectClient:
    return OpenProjectClient(
        artifact_store=SqlAlchemyOpenProjectArtifactStore(session),
        outbound_store=SqlAlchemyOpenProjectOutboundStore(session),
        reconciliation_store=SqlAlchemyOpenProjectReconciliationStore(session),
        base_url=config.openproject_base_url,
        api_key=config.openproject_api_token,
    )


async def _create_work_package(
    *,
    session,
    config: Phase9E2EConfig,
    gateway: ManagedWorkPackageGateway,
    project: Project,
    identity: PlanNodeIdentity,
    run_key: str,
) -> tuple[str, str]:
    catalog = await gateway.load_resource_catalog()
    verified_status_name = _resolve_verified_status(
        catalog,
        config.configured_verified_status,
    )
    type_link = OpenProjectSemanticMapper(
        catalog=catalog
    ).type_link_for_plan_kind(PlanNodeKind.TASK)
    if type_link is None:
        pytest.fail("OpenProject Task type mapping is unavailable")
    response = await gateway.create_or_update_work_package(
        project_id=config.openproject_project_id,
        external_idempotency_key=f"phase9:e2e:{run_key}:work-package",
        payload={
            "subject": f"Phase 9 sample_project discount {run_key[:8]}",
            "description": {
                "format": "markdown",
                "raw": (
                    "Add percentage discount support and verify it through "
                    "the Phase 9 agent flow."
                ),
            },
            "_links": {
                "type": type_link.as_hal_link(),
            },
        },
        local_project_id=project.id,
        node_identity_id=identity.id,
    )
    await session.commit()
    return str(response["id"]), verified_status_name


def _resolve_verified_status(
    catalog: OpenProjectResourceCatalog,
    configured_name: str | None,
) -> str:
    indexed = {name.lower(): name for name in catalog.status_hrefs}
    candidates = [
        configured_name,
        "Verified",
        "Closed",
        "Done",
    ]
    for candidate in candidates:
        if candidate and candidate.lower() in indexed:
            return indexed[candidate.lower()]
    pytest.fail(
        "No usable Verification completion status exists in OpenProject; "
        f"set {_VERIFIED_STATUS_ENV}"
    )


def _platform_config(verified_status_name: str) -> AgentPlatformConfig:
    config = load_agent_platform_config()
    verification = config.agents["verification"]
    settings = {
        **verification.settings,
        "openproject_verified_status_name": verified_status_name,
        "require_test_command_for_pass": True,
        "require_test_evidence_for_source_changes": True,
    }
    agents = {
        **config.agents,
        "verification": verification.model_copy(
            deep=True,
            update={"settings": settings},
        ),
    }
    return config.model_copy(deep=True, update={"agents": agents})


def _implemented_main() -> str:
    return """from services.payment import PaymentService


def calculate_total(items, discount_percentage=0):
    subtotal = sum(item.price for item in items)
    return subtotal * (1 - discount_percentage / 100)


def checkout(cart):
    amount = calculate_total(
        cart.items,
        getattr(cart, "discount_percentage", 0),
    )
    payment = PaymentService()
    payment.charge(amount)
"""


def _implemented_tests() -> str:
    return """from types import SimpleNamespace

from main import calculate_total


def test_calculate_total_applies_discount_percentage():
    items = [SimpleNamespace(price=80), SimpleNamespace(price=20)]

    assert calculate_total(items, discount_percentage=15) == 85
"""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"Set {name} to run the Phase 9 OpenProject E2E test")
    return value


def _run_migrations(database_url: str) -> None:
    package_root = Path(__file__).resolve().parents[2] / "planning_agent_core"
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=package_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def _git(root: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
