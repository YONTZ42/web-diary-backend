# your_app/services/rembg_processor.py
import base64
import json
import os
import traceback
import uuid
from typing import Any

# onnxruntime import/rembg import より前
os.environ.setdefault("U2NET_HOME", "/app/.u2net")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import boto3
import requests
from botocore.config import Config
from rembg import new_session, remove

MODEL_NAME = os.environ.get("MODEL_NAME", "isnet-general-use")
DEFAULT_BUCKET = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "removed_bg/")

# 速度優先なら基本 false
ALPHA_MATTING = os.environ.get("ALPHA_MATTING", "false").lower() == "true"
ALPHA_MATTING_FOREGROUND_THRESHOLD = int(os.environ.get("AM_FG_THRESHOLD", "240"))
ALPHA_MATTING_BACKGROUND_THRESHOLD = int(os.environ.get("AM_BG_THRESHOLD", "10"))
ALPHA_MATTING_ERODE_SIZE = int(os.environ.get("AM_ERODE_SIZE", "10"))

s3 = boto3.client(
    "s3",
    config=Config(
        max_pool_connections=20,
        retries={"max_attempts": 3, "mode": "standard"},
    ),
)

http = requests.Session()

"""
SESSION = new_session(
    model_name=MODEL_NAME,
    providers=["CPUExecutionProvider"],
)
"""
ALLOWED_MODELS = {
        "isnet-general-use": "isnet-general-use",
        "isnet-anime": "isnet-anime",
        "birefnet-general-lite": "birefnet-general-lite"
    }


def process_event(event: dict[str, Any]) -> dict[str, Any]:
    params = event
    if "body" in event and isinstance(event["body"], str):
        try:
            params = json.loads(event["body"])
        except json.JSONDecodeError:
            return _response(400, {"error": "Invalid JSON body"})

    if params.get("only_for_boot"):
        return _response(200, "Hello, I am Rembg (IS-Net)!")

    try:        
        img_bytes = _get_image_data(params)

        path_params = event.get("pathParameters", {}).get("model_name", "isnet-general-use") 
        model_type=ALLOWED_MODELS.get(path_params, "isnet-general-use")
        SESSION = new_session(
            model_name=model_type,
            providers=["CPUExecutionProvider"],
        )  
        output_bytes = remove(
            img_bytes,
            session=SESSION,
            alpha_matting=ALPHA_MATTING,
            alpha_matting_foreground_threshold=ALPHA_MATTING_FOREGROUND_THRESHOLD,
            alpha_matting_background_threshold=ALPHA_MATTING_BACKGROUND_THRESHOLD,
            alpha_matting_erode_size=ALPHA_MATTING_ERODE_SIZE,
        )

        dest_bucket = DEFAULT_BUCKET
        dest_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"
        output_url = _put_to_s3(output_bytes, dest_bucket, dest_key)

        return _response(200, {"processed_url": output_url})

    except Exception as e:
        print(f"[rembg] Error: {str(e)}")
        traceback.print_exc()
        return _response(500, {"error": str(e)})

def _get_image_data(params: dict[str, Any]) -> bytes:
    if "image_data" in params:
        data_str = params["image_data"]
        encoded = data_str.split(",", 1)[1] if "," in data_str else data_str
        return base64.b64decode(encoded)

    if "image_url" in params:
        res = http.get(params["image_url"], timeout=(3, 20))
        res.raise_for_status()
        return res.content

    bucket = params.get("bucket")
    key = params.get("key")
    if bucket and key:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    raise ValueError("No valid image source provided.")

def _put_to_s3(buffer: bytes, bucket: str, key: str) -> str:
    if not bucket:
        raise ValueError("Environment variable AWS_STORAGE_BUCKET_NAME is not set.")

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer,
        ContentType="image/png",
    )

    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,
    )

def _response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "body": json.dumps(body, ensure_ascii=False),
    }