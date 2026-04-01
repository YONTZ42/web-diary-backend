from __future__ import annotations

import os

import boto3
import pytest
from moto import mock_aws
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def user_password() -> str:
    return "password123"


@pytest.fixture
def user(user_password):
    return UserFactory(password=user_password)


@pytest.fixture
def other_user(user_password):
    return UserFactory(password=user_password)


@pytest.fixture
def user_token(user):
    return str(RefreshToken.for_user(user).access_token)


@pytest.fixture
def user_client(user_token) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {user_token}")
    return client


@pytest.fixture
def guest_id() -> str:
    return "guest-test-001"


@pytest.fixture
def guest_headers(guest_id) -> dict[str, str]:
    return {"HTTP_X_GUEST_ID": guest_id}


@pytest.fixture
def guest_client(guest_headers) -> APIClient:
    client = APIClient()
    client.credentials(**guest_headers)
    return client


@pytest.fixture
def s3_env(settings):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_REGION_NAME = "us-east-1"
    settings.AWS_REGION = "us-east-1"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    yield settings


@pytest.fixture
def mocked_s3(s3_env):
    with mock_aws():
        region = s3_env.AWS_S3_REGION_NAME
        bucket = s3_env.AWS_STORAGE_BUCKET_NAME
        s3 = boto3.client("s3", region_name=region)
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        yield s3
