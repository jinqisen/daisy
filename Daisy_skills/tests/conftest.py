import pytest
import os
import sys
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    os.environ["ADMIN_TOKENS"] = "admin_token_123"
    os.environ["ADMIN_TOOLS_ENABLED"] = "true"
    
    import app.core.config as config_module
    import importlib
    importlib.reload(config_module)
    
    yield
    del os.environ["ADMIN_TOKENS"]
    del os.environ["ADMIN_TOOLS_ENABLED"]
    importlib.reload(config_module)
