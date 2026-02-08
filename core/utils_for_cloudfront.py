import datetime
import time
import json
import base64

from django.conf import settings
from botocore.signers import CloudFrontSigner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives import hashes

def _rsa_signer(message: bytes) -> bytes:
    if settings.CLOUDFRONT_PRIVATE_KEY:
        private_key_pem = settings.CLOUDFRONT_PRIVATE_KEY.encode('utf-8')
        private_key = serialization.load_pem_private_key(
            private_key_pem,
            password=None
        )
    else:
        with open(settings.CLOUDFRONT_PRIVATE_KEY_PATH, "rb") as f:
            private_key = serialization.load_pem_private_key(f.read(), password=None)
    return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())

def generate_cf_signed_url(s3_key: str, expires_seconds: int | None = None) -> str:
    expires = expires_seconds or settings.CLOUDFRONT_URL_EXPIRES_SECONDS
    url = f"https://{settings.CLOUDFRONT_DOMAIN}/{s3_key.lstrip('/')}"
    signer = CloudFrontSigner(settings.CLOUDFRONT_PUBLIC_KEY_ID, _rsa_signer)
    return signer.generate_presigned_url(
        url,
        date_less_than=datetime.datetime.now() + datetime.timedelta(seconds=expires),
    )

def get_cloudfront_signed_cookies(url_prefix, expire_minutes=60):
    """
    指定されたURLプレフィックス（例: https://cdn.example.com/*）に対する署名付きクッキーを生成する
    """
    expires = int(time.time()) + (expire_minutes * 60)
    
    # Policyの作成 (カスタムポリシー)
    policy_dict = {
        "Statement": [
            {
                "Resource": url_prefix,
                "Condition": {
                    "DateLessThan": {"AWS:EpochTime": expires}
                }
            }
        ]
    }
    # JSON -> 文字列 -> 空白削除
    policy_json = json.dumps(policy_dict).replace(" ", "")
    
    # Base64エンコード (URLセーフ)
    policy_b64 = base64.b64encode(policy_json.encode('utf-8')).decode('utf-8').replace('+', '-').replace('=', '_').replace('/', '~')

    # 署名の作成
    private_key_pem = settings.CLOUDFRONT_PRIVATE_KEY.encode('utf-8')
    private_key = serialization.load_pem_private_key(
        private_key_pem,
        password=None
    )
    
    signature = private_key.sign(
        policy_json.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    
    signature_b64 = base64.b64encode(signature).decode('utf-8').replace('+', '-').replace('=', '_').replace('/', '~')

    return {
        'CloudFront-Policy': policy_b64,
        'CloudFront-Signature': signature_b64,
        'CloudFront-Key-Pair-Id': settings.CLOUDFRONT_KEY_PAIR_ID,
        'Expires': expires
    }
