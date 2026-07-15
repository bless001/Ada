import weaviate
from weaviate.classes.config import Configure, DataType, Property

from planning_agent_core.config import settings


class WeaviateSchemaStore:
    PROJECT_MEMORY = "ProjectMemory"
    PLAN_NODE_CONTEXT = "PlanNodeContext"
    CONTEXT_CAPSULE = "ContextCapsule"

    def __init__(self) -> None:
        self.client = weaviate.connect_to_custom(
            http_host=settings.weaviate_http_host,
            http_port=settings.weaviate_http_port,
            http_secure=settings.weaviate_secure,
            grpc_host=settings.weaviate_grpc_host,
            grpc_port=settings.weaviate_grpc_port,
            grpc_secure=settings.weaviate_secure,
        )

    def ensure_schema(self) -> None:
        self._ensure_project_memory()
        self._ensure_plan_node_context()
        self._ensure_context_capsule()

    def _ensure_project_memory(self) -> None:
        if self.client.collections.exists(self.PROJECT_MEMORY):
            return
        self.client.collections.create(
            name=self.PROJECT_MEMORY,
            vector_config=Configure.Vectors.self_provided(),
            properties=[
                Property(name="project_key", data_type=DataType.TEXT),
                Property(name="memory_id", data_type=DataType.TEXT),
                Property(name="source_type", data_type=DataType.TEXT),
                Property(name="title", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
                Property(name="summary", data_type=DataType.TEXT),
                Property(name="tags", data_type=DataType.TEXT_ARRAY),
            ],
        )

    def _ensure_plan_node_context(self) -> None:
        if self.client.collections.exists(self.PLAN_NODE_CONTEXT):
            return
        self.client.collections.create(
            name=self.PLAN_NODE_CONTEXT,
            vector_config=Configure.Vectors.self_provided(),
            properties=[
                Property(name="project_key", data_type=DataType.TEXT),
                Property(name="plan_version_id", data_type=DataType.TEXT),
                Property(name="plan_node_id", data_type=DataType.TEXT),
                Property(name="kind", data_type=DataType.TEXT),
                Property(name="title", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
            ],
        )

    def _ensure_context_capsule(self) -> None:
        if self.client.collections.exists(self.CONTEXT_CAPSULE):
            return
        self.client.collections.create(
            name=self.CONTEXT_CAPSULE,
            vector_config=Configure.Vectors.self_provided(),
            properties=[
                Property(name="project_key", data_type=DataType.TEXT),
                Property(name="capsule_id", data_type=DataType.TEXT),
                Property(name="plan_node_id", data_type=DataType.TEXT),
                Property(name="capsule_type", data_type=DataType.TEXT),
                Property(name="content", data_type=DataType.TEXT),
            ],
        )

    def close(self) -> None:
        self.client.close()
