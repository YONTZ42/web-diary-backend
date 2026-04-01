from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_health_endpoint_returns_200(api_client):
    response = api_client.get("/healthz")
    assert response.status_code == 200


def test_galleries_endpoint_returns_200_for_authenticated_user(user_client):
    response = user_client.get("/api/galleries/")
    assert response.status_code == 200
