import json
import os
import io
import boto3
import base64
import requests
import numpy as np
from PIL import Image
import uuid
from ultralytics import YOLO
import time

s3 = boto3.client("s3")

# ---- 環境変数から設定を取得 ----
MODEL_NAME = os.environ.get("MODEL_NAME", "yolo26n-seg.pt")
DEFAULT_BUCKET = os.environ.get("BUCKET_NAME", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "masks/")

# YOLO推論パラメータ
CONF_THRES = float(os.environ.get("CONF_THRESHOLD", "0.25"))
IOU_THRES = float(os.environ.get("IOU_THRESHOLD", "0.45"))
MAX_DET = int(os.environ.get("MAX_DET", "10"))
IMGSZ = int(os.environ.get("IMGSZ", "640"))
RETINA_MASKS = os.environ.get("RETINA_MASKS", "true").lower() == "true"

# モデルのロード
MODEL_PATH = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", "/var/task"), MODEL_NAME)
model = YOLO(MODEL_PATH)


def _log(level: str, message: str, **fields):
    payload = {
        "message": message,
        "service": os.environ.get("SERVICE_NAME", "mini-museum-yolo"),
        "stage": os.environ.get("STAGE", os.environ.get("APP_ENV", "staging")),
        "component": "lambda.yolo",
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False))


def lambda_handler(event, context):
    started_at = time.perf_counter()
    aws_request_id = getattr(context, "aws_request_id", None)

    # ---------------------------------------------------------
    # 1. パラメータの抽出 (Function URL対応)
    # ---------------------------------------------------------
    # デフォルトは event をそのままパラメータとして扱う
    params = event


    # Function URL経由(bodyがJSON文字列)の場合はパースして params に代入
    if "body" in event and isinstance(event["body"], str):
        try:
            params = json.loads(event["body"])
        except json.JSONDecodeError:
            _log(
                "error",
                "failed to parse json body",
                event="request_failed",
                error_code="INVALID_JSON_BODY",
                aws_request_id=aws_request_id,
                status_code=400,
            ) 
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    # ---------------------------------------------------------
    # 2. 処理開始
    # ---------------------------------------------------------
    if params.get("only_for_boot"):
        return {"statusCode": 200, "body": json.dumps("Hello, I am YOLO!")}

    try:
        # 抽出した params を渡して画像データを取得
        img_bytes = _get_image_data(params)
        input_source = "image_data" if "image_data" in params else "image_url" if "image_url" in params else "s3"
 
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB") # 安全のためRGB変換
        orig_size = img.size 

        _log(
            "info",
            "yolo request started",
            event="yolo_request_started",
            aws_request_id=aws_request_id,
            input_source=input_source,
            source_image_size_bytes=len(img_bytes),
            image_width=orig_size[0],
            image_height=orig_size[1],
        )

        # YOLO推論
        results = model.predict(
            source=img,
            conf=CONF_THRES,
            iou=IOU_THRES,
            max_det=MAX_DET,
            imgsz=IMGSZ,
            retina_masks=RETINA_MASKS
        )
        
        result = results[0]
        mask_urls = []

        # マスクデータの画像化と保存
        if hasattr(result, 'masks') and result.masks is not None:
            for mask_tensor in result.masks.data:
                mask_np = (mask_tensor.cpu().numpy() * 255).astype(np.uint8)
                mask_img = Image.fromarray(mask_np).resize(orig_size, resample=Image.NEAREST)
                
                buf = io.BytesIO()
                mask_img.save(buf, format="PNG")
                mask_bytes = buf.getvalue()
                
                # 保存先バケットの決定
                dest_bucket = DEFAULT_BUCKET
                dest_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"
                
                url = _put_to_s3(mask_bytes, dest_bucket, dest_key)
                mask_urls.append(url)

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _log(
            "info",
            "yolo request succeeded",
            event="yolo_request_succeeded",
            aws_request_id=aws_request_id,
            input_source=input_source,
            detected_count=len(mask_urls),
            duration_ms=duration_ms,
            status_code=200,
        )
        return {
            "statusCode": 200,
            "body": json.dumps({
                "detected_count": len(mask_urls),
                "mask_urls": mask_urls
            })
        }

    except Exception as e:
        import traceback
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _log(
            "error",
            "yolo request failed",
            event="yolo_request_failed",
            aws_request_id=aws_request_id,
            error_type=type(e).__name__,
            error_code="YOLO_REQUEST_FAILED",
            duration_ms=duration_ms,
            status_code=500,
        )
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

def _get_image_data(params):
    """
    params (dict) から画像データを抽出
    優先順位: image_data (Base64) > image_url (HTTPS) > S3イベント
    """
    # Pattern 1: Base64 data
    if "image_data" in params:
        data_str = params["image_data"]
        # "data:image/png;base64,..." ヘッダーがある場合を除去 (念のため残す)
        if "," in data_str:
            header, encoded = data_str.split(",", 1)
        else:
            encoded = data_str
        return base64.b64decode(encoded)

    # Pattern 2: CloudFront or any HTTPS URL
    if "image_url" in params:
        url = params["image_url"]
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.content

    # Pattern 3: Classic S3 Bucket/Key
    bucket = params.get("bucket")
    key = params.get("key")
    if bucket and key:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()

    raise ValueError("No valid image source (image_data, image_url, or bucket/key) provided.")

def _put_to_s3(buffer, bucket, key):
    if not bucket:
        raise ValueError("Environment variable BUCKET_NAME is not set.")
    
    s3.put_object(Bucket=bucket, Key=key, Body=buffer, ContentType="image/png")
    
    # 署名付きURLを発行して返す (有効期限1時間)
    return s3.generate_presigned_url(
        "get_object", 
        Params={"Bucket": bucket, "Key": key}, 
        ExpiresIn=3600
    )