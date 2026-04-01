from __future__ import annotations

import pytest

from tests.factories import UploadSessionFactory

pytestmark = pytest.mark.django_db


ISSUE_ENDPOINT = "/api/uploads/issue/"
CONFIRM_ENDPOINT = "/api/uploads/confirm/"


def test_upload_issue_succeeds_for_user(user_client, mocker):
    mocker.patch("boto3.client").return_value.generate_presigned_url.return_value = "https://example.com/upload"

    response = user_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "exhibit_image", "filename": "a.png", "mime_type": "image/png"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["uploadUrl"]
    assert response.data["s3Key"]
    assert response.data["uploadSessionId"]


def test_upload_issue_succeeds_for_guest(guest_client, mocker):
    mocker.patch("boto3.client").return_value.generate_presigned_url.return_value = "https://example.com/upload"

    response = guest_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "exhibit_image", "filename": "a.png", "mime_type": "image/png"},
        format="json",
    )

    assert response.status_code == 200


def test_upload_issue_rejects_invalid_purpose_at_serializer_level(user_client):
    response = user_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "evil", "filename": "a.png", "mime_type": "image/png"},
        format="json",
    )

    assert response.status_code == 400
    assert "purpose" in response.data


def test_upload_confirm_succeeds_only_when_object_exists(user_client, user, mocked_s3, mocker):
    mocker.patch("core.views_upload.boto3.client", return_value=mocked_s3)

    session = UploadSessionFactory(user=user)
    mocked_s3.put_object(Bucket="test-bucket", Key=session.s3_key, Body=b"img")

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"upload_session_id": str(session.id)},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == "confirmed"


def test_upload_confirm_returns_400_when_object_missing(user_client, user):
    session = UploadSessionFactory(user=user)

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"upload_session_id": str(session.id)},
        format="json",
    )

    assert response.status_code == 400


def test_upload_confirm_returns_404_for_owner_mismatch(user_client, other_user, mocked_s3):
    session = UploadSessionFactory(user=other_user)
    mocked_s3.put_object(Bucket="test-bucket", Key=session.s3_key, Body=b"img")

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"upload_session_id": str(session.id)},
        format="json",
    )

    assert response.status_code == 404



def test_upload_confirm_guest_path_succeeds(guest_client, guest_id, mocked_s3, mocker):
    mocker.patch("core.views_upload.boto3.client", return_value=mocked_s3)
    session = UploadSessionFactory(as_guest=True, guest_id=guest_id)
    mocked_s3.put_object(Bucket="test-bucket", Key=session.s3_key, Body=b"img")

    response = guest_client.post(
        CONFIRM_ENDPOINT,
        data={"upload_session_id": str(session.id)},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == "confirmed"
