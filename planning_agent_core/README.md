# Planning Agent Core

This is the fuller project scaffold for the planning agent.

Core concept preserved from the start:

```text
User request / README / project idea
        ↓
Document ingestion
        ↓
Chunking + structured extraction
        ↓
Clarification questions if unclear
        ↓
Versioned plan:
Vision → Capability → Epic → Story → Task
        ↓
PostgreSQL source of truth
        ↓
OpenProject artifacts
        ↓
Neo4j relationship memory
        ↓
Weaviate semantic memory
        ↓
Context capsules for future coding agents
```

## Design rule

```text
PostgreSQL = source of truth
Neo4j      = relationship intelligence
Weaviate   = semantic retrieval
OpenProject = human-facing work management
```

## Run

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d postgres neo4j weaviate
pip install -e ".[dev]"
uvicorn planning_agent_core.main:app --reload
```

## Main routes

```text
GET  /health

POST /v1/projects
GET  /v1/projects/{project_key}

POST /v1/documents/upload?project_key=coding-agent
GET  /v1/documents/{document_id}/chunks

POST /v1/planning/sessions
GET  /v1/planning/sessions/{session_id}
POST /v1/planning/sessions/{session_id}/answers
POST /v1/planning/sessions/{session_id}/draft-plan
POST /v1/planning/plan-versions/{plan_version_id}/approve

POST /v1/context/plan-nodes/{plan_node_id}/capsule

POST /v1/provisioning/projects/{project_key}
```

## Important files

```text
docs/postgres_schema.sql       Full PostgreSQL schema
docs/neo4j_schema.cypher       Neo4j constraints and projection model
docs/weaviate_schema.md        Weaviate collections
planning_agent_core/models.py  SQLAlchemy implementation for core tables
planning_agent_core/services/  Business logic
planning_agent_core/adapters/  OpenProject, Neo4j, Weaviate adapters
```

## MVP status

This is a serious MVP scaffold. It includes complete schemas and working API routes for project creation, document upload/chunking, planning sessions, question answering, plan drafting, approval, context capsule generation, and provisioning job creation.

The LLM and external systems are integration points. The code includes safe deterministic fallback planning when the local LLM endpoint is unavailable.
