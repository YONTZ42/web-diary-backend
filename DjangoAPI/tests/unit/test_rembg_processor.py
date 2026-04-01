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
    fake_s3 = mocker.Mock()
    fake_s3.put_object.return_value = {}

    mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    remove_mock = mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module.boto3, "client", return_value=fake_s3)

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
    fake_s3.put_object.assert_called_once()


def test_process_event_returns_error_payload_on_invalid_json(processor_module):
    process_event = getattr(processor_module, "process_event")
    with pytest.raises(json.JSONDecodeError):
        process_event({
            "body": "{not-json}",
            "pathParameters": {"model_name": "isnet-general-use"},
            "headers": {},
        })


def test_process_event_uses_default_model_when_path_parameter_missing(mocker, processor_module):
    fake_session = object()
    fake_s3 = mocker.Mock()
    fake_s3.put_object.return_value = {}

    new_session_mock = mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module.boto3, "client", return_value=fake_s3)

    process_event = getattr(processor_module, "process_event")
    result = process_event({
         "body": json.dumps({"image_data": base64.b64encode(b"INPUT_BYTES").decode("utf-8")}),
         "headers": {},
         "pathParameters": {},
     })

    assert isinstance(result, dict)
    new_session_mock.assert_called_once_with("isnet-general-use")
    fake_s3.put_object.assert_called_once()