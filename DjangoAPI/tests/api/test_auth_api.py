from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_issue_guest_id_returns_guest_id(api_client):
    response = api_client.post("/api/auth/guest/", data={}, format="json")

    assert response.status_code == 200
    assert response.data["guest_id"]


def test_me_requires_authentication(api_client):
    response = api_client.get("/api/me/")
    assert response.status_code == 401


def test_me_returns_current_user(user_client, user):
    response = user_client.get("/api/me/")

    assert response.status_code == 200
    assert response.data["id"] == str(user.id) or response.data["id"] == user.id
    assert response.data["email"] == user.email


def test_user_registration_creates_user(api_client):
    response = api_client.post(
        "/api/auth/register/",
        data={"email": "newuser@example.com", "password": "password123", "display_name": "New User"},
        format="json",
    )

    assert response.status_code in {200, 201}
    assert response.data["email"] == "newuser@example.com"


def test_google_login_rejects_invalid_google_token(api_client, mocker):
    mocked_verify = mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        side_effect=Exception("invalid"),
    )

    response = api_client.post(
        "/api/auth/google/",
        data={"id_token": "bad-token"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Invalid Google token"
    mocked_verify.assert_called_once()


def test_google_login_rejects_invalid_issuer(api_client, mocker, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value={
            "iss": "evil.example.com",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
        },
    )

    response = api_client.post(
        "/api/auth/google/",
        data={"id_token": "token"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Invalid token issuer"


def test_google_login_rejects_unverified_email(api_client, mocker, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value={
            "iss": "accounts.google.com",
            "email": "user@example.com",
            "email_verified": False,
            "name": "Test User",
        },
    )

    response = api_client.post(
        "/api/auth/google/",
        data={"id_token": "token"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Google account email is not verified"


def test_google_login_rejects_missing_email(api_client, mocker, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value={
            "iss": "accounts.google.com",
            "email_verified": True,
            "name": "Test User",
        },
    )

    response = api_client.post(
        "/api/auth/google/",
        data={"id_token": "token"},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == "Google account email not found"


def test_google_login_returns_access_and_refresh(api_client, mocker, settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client-id"
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value={
            "iss": "accounts.google.com",
            "email": "user@example.com",
            "email_verified": True,
            "name": "Test User",
            "picture": "https://example.com/avatar.jpg",
        },
    )

    response = api_client.post(
        "/api/auth/google/",
        data={"id_token": "token"},
        format="json",
    )

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
