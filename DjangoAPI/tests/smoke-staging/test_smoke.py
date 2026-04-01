from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db

def test_health_endpoint_returns_200_in_staging(api_client):
    response = api_client.get("/health")
    assert response.status_code == 200