from __future__ import annotations

from unittest.mock import Mock

import pytest

from tests.support._app import REMBG_PROCESSOR_MODULE, import_attr


@pytest.fixture
def processor_module():
    return __import__(REMBG_PROCESSOR_MODULE, fromlist=["*"])


def test_process_event_passes_model_and_returns_service_payload(mocker, processor_module):
    fake_session = object()
    mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    remove_mock = mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module.base64, "b64decode", return_value=b"INPUT_BYTES")
    mocker.patch.object(processor_module.base64, "b64encode", return_value=b"UE5HX0JZVEVT")

    process_event = getattr(processor_module, "process_event")
    event = {"image": "dummy-base64", "alphaMatting": True}

    result = process_event(event, model_name="isnet-general-use")

    assert result["ok"] is True
    assert result["image"] == "UE5HX0JZVEVT"
    remove_mock.assert_called_once()
    _, kwargs = remove_mock.call_args
    assert kwargs["session"] is fake_session


def test_process_event_returns_error_payload_on_exception(mocker, processor_module):
    mocker.patch.object(processor_module, "new_session", side_effect=RuntimeError("boom"))
    process_event = getattr(processor_module, "process_event")

    result = process_event({"image": "dummy-base64"}, model_name="isnet-general-use")

    assert result["ok"] is False
    assert "boom" in result["error"].lower()


def test_process_event_uses_default_model_when_not_explicit(mocker, processor_module):
    fake_session = object()
    new_session_mock = mocker.patch.object(processor_module, "new_session", return_value=fake_session)
    mocker.patch.object(processor_module, "remove", return_value=b"PNG_BYTES")
    mocker.patch.object(processor_module.base64, "b64decode", return_value=b"INPUT_BYTES")
    mocker.patch.object(processor_module.base64, "b64encode", return_value=b"UE5HX0JZVEVT")

    process_event = getattr(processor_module, "process_event")
    process_event({"image": "dummy-base64"})

    assert new_session_mock.call_args.kwargs["model_name"] == getattr(
        processor_module, "MODEL_NAME"
    )
