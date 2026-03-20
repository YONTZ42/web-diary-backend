from __future__ import annotations

import io

import pytest

from tests.factories import UploadSessionFactory

pytestmark = pytest.mark.django_db


ISSUE_ENDPOINT = "/api/uploads/issue/"
CONFIRM_ENDPOINT = "/api/uploads/confirm/"


def test_upload_issue_succeeds_for_user(user_client):
    response = user_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "exhibit_image", "fileName": "a.png", "contentType": "image/png"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data.get("uploadUrl") or response.data.get("upload_url")


def test_upload_issue_succeeds_for_guest(guest_client):
    response = guest_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "exhibit_image", "fileName": "a.png", "contentType": "image/png"},
        format="json",
    )

    assert response.status_code == 200


def test_upload_issue_rejects_invalid_purpose(user_client):
    response = user_client.post(
        ISSUE_ENDPOINT,
        data={"purpose": "evil", "fileName": "a.png", "contentType": "image/png"},
        format="json",
    )

    assert response.status_code in {400, 422}


def test_upload_confirm_succeeds_only_when_object_exists(user_client, user, mocked_s3, s3_env):
    session = UploadSessionFactory(user=user, bucket=s3_env.AWS_STORAGE_BUCKET_NAME)
    mocked_s3.put_object(Bucket=session.bucket, Key=session.object_key, Body=b"img")

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"uploadSessionId": str(session.id)},
        format="json",
    )

    assert response.status_code == 200


def test_upload_confirm_returns_400_when_object_missing(user_client, user, mocked_s3, s3_env):
    session = UploadSessionFactory(user=user, bucket=s3_env.AWS_STORAGE_BUCKET_NAME)

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"uploadSessionId": str(session.id)},
        format="json",
    )

    assert response.status_code == 400


def test_upload_confirm_returns_404_for_owner_mismatch(user_client, other_user, mocked_s3, s3_env):
    session = UploadSessionFactory(user=other_user, bucket=s3_env.AWS_STORAGE_BUCKET_NAME)
    mocked_s3.put_object(Bucket=session.bucket, Key=session.object_key, Body=b"img")

    response = user_client.post(
        CONFIRM_ENDPOINT,
        data={"uploadSessionId": str(session.id)},
        format="json",
    )

    assert response.status_code == 404


def test_upload_confirm_guest_path_succeeds(guest_client, guest_id, mocked_s3, s3_env):
    session = UploadSessionFactory(as_guest=True, guest_id=guest_id, bucket=s3_env.AWS_STORAGE_BUCKET_NAME)
    mocked_s3.put_object(Bucket=session.bucket, Key=session.object_key, Body=b"img")

    response = guest_client.post(
        CONFIRM_ENDPOINT,
        data={"uploadSessionId": str(session.id)},
        format="json",
    )

    assert response.status_code == 200
