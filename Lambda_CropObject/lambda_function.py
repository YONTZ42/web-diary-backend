import os
import json
import base64
import hashlib
from urllib.parse import urlparse, unquote


import boto3
import requests

os.environ['NUMBA_CACHE_DIR'] = '/tmp'
os.environ['MPLCONFIGDIR'] = '/tmp'
s3 = boto3.client("s3")

OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]                # 出力先バケット
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "removed/")  # 任意
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")      # 例: https://assets.example.com  (空ならS3直)
RETURN_PRESIGNED = os.environ.get("RETURN_PRESIGNED", "0") == "1"
PRESIGNED_EXPIRES = int(os.environ.get("PRESIGNED_EXPIRES", "3600"))

# 入力（API Gateway / Function URL / 直invoke）の差を吸収
def _parse_payload(event):
    body = event.get("body")
    if body is None:
        # 直invoke等で event 自体がpayloadのケース
        return event
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body or {}

def _safe_basename_from_url(url: str) -> str:
    u = urlparse(url)
    base = os.path.basename(unquote(u.path)) or "image"
    # 拡張子を除いた名前だけを取りたい
    name, dot, ext = base.rpartition(".")
    return name if dot else base

def _make_output_key(image_url: str) -> str:
    # 衝突回避のためURLハッシュを混ぜる（同一URLなら同一keyにもできる）
    h = hashlib.sha256(image_url.encode("utf-8")).hexdigest()[:12]
    name = _safe_basename_from_url(image_url)
    return f"{OUTPUT_PREFIX}{name}-{h}.png"

def _download_image(url: str) -> bytes:
    # presigned URL含めてHTTP GETできればOK
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content

def _put_png(bucket: str, key: str, png_bytes: bytes):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=png_bytes,
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
    )

def _s3_public_url(bucket: str, key: str) -> str:
    # バケットがpublic、またはCloudFront等で到達できる前提
    return f"https://{bucket}.s3.amazonaws.com/{key}"

def _cloudfront_or_public_url(key: str) -> str:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}/{key}"
    return _s3_public_url(OUTPUT_BUCKET, key)

def _presigned_get_url(bucket: str, key: str) -> str:
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=PRESIGNED_EXPIRES,
    )

def lambda_handler(event, context):
    from rembg import remove
    try:
        payload = _parse_payload(event)
        image_url = payload.get("image_url")
        if not image_url:
            return {
                "statusCode": 400,
                "headers": {"content-type": "application/json; charset=utf-8"},
                "body": json.dumps({"error": "image_url is required"}, ensure_ascii=False),
            }

        # 1) 画像取得（バイナリのまま扱う。decodeしない）
        img_bytes = _download_image(image_url)

        # 2) 背景除去（PNG相当のバイナリが返る）
        out_png = remove(img_bytes)

        # 3) S3保存
        out_key = _make_output_key(image_url)
        _put_png(OUTPUT_BUCKET, out_key, out_png)

        # 4) URL返却
        if RETURN_PRESIGNED:
            result_url = _presigned_get_url(OUTPUT_BUCKET, out_key)
        else:
            result_url = _cloudfront_or_public_url(out_key)

        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json; charset=utf-8"},
            "body": json.dumps(
                {"result_bucket": OUTPUT_BUCKET, "result_key": out_key, "result_url": result_url},
                ensure_ascii=False,
            ),
        }

    except requests.HTTPError as e:
        return {
            "statusCode": 502,
            "headers": {"content-type": "application/json; charset=utf-8"},
            "body": json.dumps({"error": "failed_to_fetch_image", "detail": str(e)}, ensure_ascii=False),
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"content-type": "application/json; charset=utf-8"},
            "body": json.dumps({"error": "internal_error", "detail": str(e)}, ensure_ascii=False),
        }