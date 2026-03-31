from __future__ import annotations

import json

import pytest

from tests.support._app import VIEWS_REMBG_MODULE

pytestmark = pytest.mark.django_db


ENDPOINT = "/api/image/rembg/isnet-general-use/"


def test_rembg_api_builds_lambda_like_event_and_calls_service(api_client, mocker):
    mocked = mocker.patch(f"{VIEWS_REMBG_MODULE}.process_event", return_value={"ok": True, "image": "xxx"})

    payload = {"image_data": "base64data", "alpha_matting": True}
    response = api_client.post(ENDPOINT, data=payload, format="json", HTTP_X_GUEST_ID="guest-123")

    assert response.status_code == 200
    mocked.assert_called_once()
    event = mocked.call_args.args[0]
    assert event["httpMethod"] == "POST"
    assert event["pathParameters"]["model_name"] == "isnet-general-use"
    assert json.loads(event["body"])["image_data"] == "base64data"
    assert mocked.call_args.kwargs["logger"] is not None


def test_rembg_api_returns_500_when_service_raises(api_client, mocker):
    mocker.patch(f"{VIEWS_REMBG_MODULE}.process_event", side_effect=RuntimeError("bad"))

    response = api_client.post(
        ENDPOINT,
        data={"image_data": "base64data"},
        format="json",
    )

    assert response.status_code == 500
    assert response.data["error"] == "Internal Server Error"


def test_rembg_api_rejects_invalid_json_body(api_client):
    response = api_client.generic(
        "POST",
        ENDPOINT,
        data=b"{not-json}",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.data["error"] == "Invalid JSON body"
