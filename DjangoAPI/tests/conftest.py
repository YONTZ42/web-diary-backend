from __future__ import annotations

import os

#from DjangoAPI.config import settings
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
    region = "ap-northeast-1"
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_REGION_NAME = region
    settings.AWS_REGION = region

# boto3クライアントが参照する環境変数をテスト用に固定する
    os.environ["AWS_DEFAULT_REGION"] = region
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    
    yield settings


@pytest.fixture
def mocked_s3(s3_env):
    with mock_aws():
        region = s3_env.AWS_S3_REGION_NAME
        bucket = s3_env.AWS_STORAGE_BUCKET_NAME
        s3 = boto3.client("s3", region_name=region)

        config = {"LocationConstraint": region} if region != "us-east-1" else {} 
        
        if config:
            s3.create_bucket(Bucket=bucket, CreateBucketConfiguration=config)
        else:
            s3.create_bucket(Bucket=bucket)
            
        yield s3