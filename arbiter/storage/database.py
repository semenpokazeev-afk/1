"""
ARBITER Storage: Async SQLite Database Engine with WAL Mode
"""

import aiosqlite
import logging
import os
from typing import AsyncGenerator
from arbiter.core.config import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.database_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


async def get_db_connection() -> aiosqlite.Connection:
    """
    Creates an async SQLite connection with WAL (Write-Ahead Logging) and foreign keys enabled.
    """
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


async def init_db() -> None:
    """
    Initializes the database schema and indexes.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        
        # Requests table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            task_category TEXT NOT NULL,
            strategy TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            estimated_cost REAL NOT NULL,
            budget_limit REAL
        );
        """)

        # Provider calls table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS provider_calls (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            status TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            actual_cost REAL NOT NULL,
            quality_score REAL NOT NULL,
            was_selected BOOLEAN NOT NULL DEFAULT 0,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        );
        """)

        # Feedback table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        );
        """)

        # Bandit state table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS bandit_state (
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            task_category TEXT NOT NULL,
            alpha REAL NOT NULL DEFAULT 1.0,
            beta REAL NOT NULL DEFAULT 1.0,
            total_trials INTEGER NOT NULL DEFAULT 0,
            last_updated TEXT NOT NULL,
            PRIMARY KEY (provider, model, task_category)
        );
        """)

        # Traces table for Replay & Debug mode
        await db.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            response_text TEXT NOT NULL,
            trace_data TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(request_id) REFERENCES requests(id) ON DELETE CASCADE
        );
        """)

        # Indices for fast analytics
        await db.execute("CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_requests_category ON requests(task_category);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_provider_calls_req ON provider_calls(request_id);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_provider_calls_model ON provider_calls(model);")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_feedback_request ON feedback(request_id);")

        await db.commit()
    logger.info(f"Database schema initialized successfully at {DB_PATH}")
