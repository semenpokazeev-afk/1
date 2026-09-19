"""
ARBITER Master FastAPI Application Gateway (Module 1)
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from arbiter.core.config import settings
from arbiter.core.events import bus
from arbiter.storage.database import init_db
from arbiter.router.mab import mab_engine
from arbiter.classifier import classifier
from arbiter.gateway.routes_v1 import v1_router
from arbiter.gateway.routes_feedback import feedback_router
from arbiter.gateway.routes_analytics import analytics_router
from arbiter.gateway.routes_ws import ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("arbiter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing ARBITER subsystems...")
    await init_db()
    await mab_engine.initialize()
    await bus.start()
    await classifier.self_trainer.start()
    logger.info("ARBITER is fully online and accepting requests.")
    
    yield

    # Shutdown
    logger.info("Shutting down ARBITER subsystems...")
    await classifier.self_trainer.stop()
    await bus.stop()
    logger.info("ARBITER shutdown complete.")


app = FastAPI(
    title="ARBITER Intelligence Router",
    description="Adaptive Multi-Model Intelligence Router with MAB and Zero-LLM Classification",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Include API routes
app.include_router(v1_router)
app.include_router(feedback_router)
app.include_router(analytics_router)
app.include_router(ws_router)

# Static Dashboard Mount
static_dir = os.path.join(os.path.dirname(__file__), "..", "dashboard", "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "name": settings.app_name,
        "status": "healthy",
        "docs_url": "/docs",
        "dashboard": "/static/index.html"
    }
