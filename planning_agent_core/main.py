from contextlib import asynccontextmanager

from fastapi import FastAPI

from planning_agent_core import models as _models  # noqa: F401
from planning_agent_core.api.context import router as context_router
from planning_agent_core.api.documents import router as documents_router
from planning_agent_core.api.planning import router as planning_router
from planning_agent_core.api.projects import router as projects_router
from planning_agent_core.api.provisioning import router as provisioning_router
from planning_agent_core.db import create_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_schema()
    yield


app = FastAPI(title="Planning Agent Core", version="0.2.0", lifespan=lifespan)
app.include_router(projects_router)
app.include_router(documents_router)
app.include_router(planning_router)
app.include_router(context_router)
app.include_router(provisioning_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
