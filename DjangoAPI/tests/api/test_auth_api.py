from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db


def test_issue_guest_id_returns_guest_id(api_client):
    response = api_client.post("/api/auth/guest/", data={}, format="json")

    assert response.status_code == 200
    assert response.data.get("guestId") or response.data.get("guest_id")


def test_token_issue_succeeds_for_valid_credentials(api_client, user, user_password):
    response = api_client.post(
        "/api/token/",
        data={"username": user.username, "password": user_password},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data


def test_token_issue_rejects_invalid_credentials(api_client, user):
    response = api_client.post(
        "/api/token/",
        data={"username": user.username, "password": "wrong-password"},
        format="json",
    )

    assert response.status_code in {400, 401}


def test_token_refresh_succeeds(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = str(RefreshToken.for_user(user))
    response = api_client.post("/api/token/refresh/", data={"refresh": refresh}, format="json")

    assert response.status_code == 200
    assert "access" in response.data


def test_me_requires_authentication(api_client):
    response = api_client.get("/api/me/")
    assert response.status_code == 401


def test_me_returns_current_user(user_client, user):
    response = user_client.get("/api/me/")

    assert response.status_code == 200
    assert response.data["id"] == str(user.id) or response.data["id"] == user.id
