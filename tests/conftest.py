"""
Pytest fixtures and configuration for ARBITER test suite.
"""

import os
import sys
import pytest
import asyncio

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Force test database URL
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_arbiter.db"


@pytest.fixture(autouse=True, scope="session")
def setup_test_db():
    from arbiter.storage.database import init_db
    asyncio.run(init_db())
    yield
    if os.path.exists("./test_arbiter.db"):
        try:
            os.remove("./test_arbiter.db")
        except Exception:
            pass
