from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_rembg_api_passes_payload_to_service(api_client, mocker):
    mocked = mocker.patch("museum.views.process_event", return_value={"ok": True, "image": "xxx"})

    payload = {"image": "base64data", "alphaMatting": True}
    response = api_client.post("/api/image/rembg/isnet-general-use/", data=payload, format="json")

    assert response.status_code == 200
    mocked.assert_called_once()
    assert mocked.call_args.args[0] == payload
    assert mocked.call_args.kwargs["model_name"] == "isnet-general-use"


def test_rembg_api_returns_service_status(api_client, mocker):
    mocker.patch("museum.views.process_event", return_value={"ok": False, "error": "bad", "status": 400})

    response = api_client.post(
        "/api/image/rembg/isnet-general-use/",
        data={"image": "base64data"},
        format="json",
    )

    assert response.status_code == 400
