# your_app/services/rembg_processor.py
import base64
import json
import os
import traceback
import uuid
from typing import Any
import time

# onnxruntime import/rembg import より前
os.environ.setdefault("U2NET_HOME", "/app/.u2net")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import boto3
import requests
from botocore.config import Config
from rembg import new_session, remove
from config.logging_utils import get_logger, log_exception

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


def process_event(event: dict[str, Any], *, logger=None) -> dict[str, Any]:
    logger = logger or get_logger("django.rembg").bind(component="django.rembg")
    started_at = time.perf_counter()

    try:
        body = event.get("body") or "{}"
        if isinstance(body, str):
            params = json.loads(body)
        else:
            params = body
    except Exception:
        log_exception(
            logger,
            event_type="rembg_input_decode_failed",
            message="failed to parse request body",
            error_code="REMBG_INVALID_JSON",
            status_code=400,
        )
        raise

    model_name = (
        event.get("pathParameters", {}).get("model_name")
        or params.get("model_name")
        or MODEL_NAME
    )


    request_context = event.get("requestContext", {}) or {}
    logger = logger.bind(
        model_name=model_name,
        request_id=request_context.get("request_id"),
        guest_id=request_context.get("guest_id"),
        user_id=request_context.get("user_id"),
    )

    image_bytes = None
    input_source = "unknown"

    try:
        if params.get("image_data"):
            input_source = "image_data"
            raw = params["image_data"]
            encoded = raw.split(",", 1)[1] if "," in raw else raw
            image_bytes = base64.b64decode(encoded)
        elif params.get("image_url"):
            input_source = "image_url"
            resp = requests.get(params["image_url"], timeout=20)
            resp.raise_for_status()
            image_bytes = resp.content
        elif params.get("bucket") and params.get("key"):
            input_source = "s3"
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=params["bucket"], Key=params["key"])
            image_bytes = obj["Body"].read()
        else:
            raise ValueError("No valid image source provided")
    except Exception:
        log_exception(
            logger.bind(input_source=input_source),
            event_type="rembg_image_fetch_failed",
            message="failed to load input image",
            error_code="REMBG_IMAGE_FETCH_FAILED",
            status_code=400,
        )
        raise

    source_image_size_bytes = len(image_bytes) if image_bytes else 0

    try:
        logger.info(
            "initializing rembg model session",
            event_type="rembg_model_init_started",
            input_source=input_source,
            source_image_size_bytes=source_image_size_bytes,
        )
        session = new_session(model_name)
        logger.info(
            "rembg model session initialized",
            event_type="rembg_model_init_succeeded",
            input_source=input_source,
            source_image_size_bytes=source_image_size_bytes,
        )
    except Exception:
        log_exception(
            logger.bind(input_source=input_source, source_image_size_bytes=source_image_size_bytes),
            event_type ="rembg_model_init_failed",
            message="failed to initialize rembg session",
            error_code="REMBG_MODEL_INIT_FAILED",
            status_code=500,
        )
        raise


    try:
        logger.info(
            "running rembg inference",
            event_type="rembg_inference_started",
            input_source=input_source,
            source_image_size_bytes=source_image_size_bytes,
        )
        output = remove(
            image_bytes,
            session=session,
        )
    except Exception:
        print("Failed during rembg inference")
        traceback.print_exc()
        log_exception(
            logger.bind(input_source=input_source, source_image_size_bytes=source_image_size_bytes),
            event_type="rembg_inference_failed",
            message="rembg inference failed",
            error_code="REMBG_INFERENCE_FAILED",
            status_code=500,
        )
        raise


    s3 = boto3.client("s3")
    key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"

    try:
        s3.put_object(
            Bucket=DEFAULT_BUCKET,
            Key=key,
            Body=output,
            ContentType="image/png",
        )
    except Exception:
        log_exception(
            logger.bind(
                input_source=input_source,
                source_image_size_bytes=source_image_size_bytes,
                s3_bucket=DEFAULT_BUCKET,
                s3_key=key,
            ),
            event_type="rembg_s3_put_failed",
            message="failed to put rembg output to S3",
            error_code="REMBG_S3_PUT_FAILED",
            status_code=500,
        )
        raise

    try:
        presigned_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': DEFAULT_BUCKET, 'Key': key},
            ExpiresIn=3600  # 3600秒 = 1時間
        )
    except Exception as e:
        # URL生成に失敗した場合のログなど
        presigned_url = None
        
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info(
        "rembg processing completed",
        event_type="rembg_processing_succeeded",
        message="rembg processing completed successfully",
        input_source=input_source,
        source_image_size_bytes=source_image_size_bytes,
        s3_bucket=DEFAULT_BUCKET,
        s3_key=key,
        duration_ms=duration_ms,
        status_code=200,
    )

    return {
        "success": True,
        "bucket": DEFAULT_BUCKET,
        "key": key,
        "processed_url": presigned_url,
    }