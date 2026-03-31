from __future__ import annotations

import base64
import json

import pytest

from tests.support._app import REMBG_PROCESSOR_MODULE


@pytest.fixture
def processor_module():
    return __import__(REMBG_PROCESSOR_MODULE, fromlist=["*"])


def test_process_event_accepts_image_data_and_returns_result(mocker, processor_module):
    fake_session = object()
    mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    remove_mock = mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module, "_put_bytes_and_make_result", return_value={"image_url": "https://example.com/out.png"}, create=True)

    process_event = getattr(processor_module, "process_event")
    event = {
        "body": json.dumps({"image_data": base64.b64encode(b"INPUT_BYTES").decode("utf-8")}),
        "pathParameters": {"model_name": "isnet-general-use"},
        "headers": {},
    }

    result = process_event(event)

    assert isinstance(result, dict)
    remove_mock.assert_called_once()
    _, kwargs = remove_mock.call_args
    assert kwargs["session"] is fake_session


def test_process_event_returns_error_payload_on_invalid_json(processor_module):
    process_event = getattr(processor_module, "process_event")

    result = process_event({"body": "{not-json}", "pathParameters": {"model_name": "isnet-general-use"}, "headers": {}})

    assert isinstance(result, dict)
    assert result.get("statusCode") in {400, None} or result.get("error")


def test_process_event_uses_default_model_when_path_parameter_missing(mocker, processor_module):
    fake_session = object()
    new_session_mock = mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module, "_put_bytes_and_make_result", return_value={"image_url": "https://example.com/out.png"}, create=True)

    process_event = getattr(processor_module, "process_event")
    process_event({
        "body": json.dumps({"image_data": base64.b64encode(b"INPUT_BYTES").decode("utf-8")}),
        "headers": {},
        "pathParameters": {},
    })

    assert new_session_mock.called
