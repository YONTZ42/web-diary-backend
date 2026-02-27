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
from urllib.parse import urlparse

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

def lambda_handler(event, context):
    if event.get("only_for_boot"):
        return {"statusCode": 200, "body": json.dumps("Hello, I am YOLO!")}

    try:
        # 1. 画像の取得 (Base64 or URL or S3)
        img_bytes = _get_image_data(event)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB") # 安全のためRGB変換
        orig_size = img.size 
        
        # 2. YOLO推論
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

        # 3. マスクデータの画像化と保存
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

        return {
            "statusCode": 200,
            "body": json.dumps({
                "detected_count": len(mask_urls),
                "mask_urls": mask_urls
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

def _get_image_data(event):
    """
    優先順位: image_data (Base64) > image_url (HTTPS) > S3イベント
    """
    # Pattern 1: Base64 data
    if "image_data" in event:
        # "data:image/png;base64,..." のようなヘッダーがある場合を除去
        header, encoded = event["image_data"].split(",", 1) if "," in event["image_data"] else (None, event["image_data"])
        return base64.b64decode(encoded)

    # Pattern 2: CloudFront or any HTTPS URL
    if "image_url" in event:
        url = event["image_url"]
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        return res.content

    # Pattern 3: Classic S3 Bucket/Key
    bucket = event.get("bucket")
    key = event.get("key")
    if bucket and key:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()

    raise ValueError("No valid image source (image_data, image_url, or bucket/key) provided.")

def _put_to_s3(buffer, bucket, key):
    if not bucket:
        raise ValueError("Environment variable BUCKET_NAME is not set.")
    s3.put_object(Bucket=bucket, Key=key, Body=buffer, ContentType="image/png")
    # マスク画像もCloudFront経由で返したい場合はここを調整
    return s3.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600)