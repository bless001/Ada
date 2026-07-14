from neo4j import AsyncGraphDatabase
from planning_agent_core.config import settings


class Neo4jProjectionStore:
    def __init__(self) -> None:
        self.driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_username, settings.neo4j_password))

    async def ensure_constraints(self) -> None:
        statements = [
            "CREATE CONSTRAINT project_key_unique IF NOT EXISTS FOR (p:Project) REQUIRE p.project_key IS UNIQUE",
            "CREATE CONSTRAINT plan_version_id_unique IF NOT EXISTS FOR (v:PlanVersion) REQUIRE v.id IS UNIQUE",
            "CREATE CONSTRAINT plan_node_id_unique IF NOT EXISTS FOR (n:PlanNode) REQUIRE n.id IS UNIQUE",
        ]
        for statement in statements:
            await self.driver.execute_query(statement, database_=settings.neo4j_database)

    async def close(self) -> None:
        await self.driver.close()
