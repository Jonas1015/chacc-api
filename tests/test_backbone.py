"""
Unit tests for ChaCC API Backbone.
"""

import pytest
from fastapi.testclient import TestClient

from chacc_api.server.main import app


@pytest.fixture
def client():
    """Test client fixture."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ChaCC" in response.text
    assert "Swagger UI" in response.text
    assert "ReDoc" in response.text


def test_docs_endpoint(client):
    """Test the docs endpoint."""
    response = client.get("/docs")
    assert response.status_code == 200
