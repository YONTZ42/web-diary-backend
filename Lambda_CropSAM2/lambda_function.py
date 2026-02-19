import base64
import json
import os
import io
import boto3
import numpy as np
from PIL import Image
import uuid
from ultralytics import YOLO
from urllib.parse import urlparse

s3 = boto3.client("s3")

# ---- 環境変数から設定を取得 ----
MODEL_NAME = os.environ.get("MODEL_NAME", "yolo26n-seg.pt")
DEFAULT_BUCKET = os.environ.get("BUCKET_NAME", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "cutouts/")

# YOLO推論パラメータ (環境変数で動的に変更可能)
CONF_THRES = float(os.environ.get("CONF_THRESHOLD", "0.25"))
IOU_THRES = float(os.environ.get("IOU_THRESHOLD", "0.45"))
MAX_DET = int(os.environ.get("MAX_DET", "10"))
IMGSZ = int(os.environ.get("IMGSZ", "640"))
RETINA_MASKS = os.environ.get("RETINA_MASKS", "true").lower() == "true"

# モデルのロード
MODEL_PATH = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", "/var/task"), MODEL_NAME)
model = YOLO(MODEL_PATH)

def lambda_handler(event, context):
    try:
        # 1. eventからS3情報を取得して画像をダウンロード
        # event 形式例: {"s3_url": "s3://bucket-name/path/to/image.jpg"} 
        # もしくは直接 bucket と key を指定する場合も考慮
        bucket, key = _parse_s3_event(event)
        response = s3.get_object(Bucket=bucket, Key=key)
        img_bytes = response['Body'].read()
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        
        # 2. YOLO推論 (環境変数のパラメータを適用)
        results = model.predict(
            source=img,
            conf=CONF_THRES,
            iou=IOU_THRES,
            max_det=MAX_DET,
            imgsz=IMGSZ,
            retina_masks=RETINA_MASKS
        )
        
        result = results[0]
        s3_urls = []

        # 3. 検出された全物体をループで処理
        if hasattr(result, 'masks') and result.masks is not None:
            for mask_data in result.masks.data:
                mask_np = mask_data.cpu().numpy()
                
                # 背景透過処理
                out_png_bytes = _apply_mask_to_image(img, mask_np)
                
                # 結果をS3に保存 (保存先バケットは環境変数または入力と同じもの)
                dest_bucket = DEFAULT_BUCKET or bucket
                dest_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"
                
                url = _put_to_s3(out_png_bytes, dest_bucket, dest_key)
                s3_urls.append(url)

        # 4. JSONレスポンス (URLのリストを返す)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "detected_count": len(s3_urls),
                "urls": s3_urls,
                "input_source": f"s3://{bucket}/{key}",
                "config_used": {
                    "conf": CONF_THRES,
                    "max_det": MAX_DET,
                    "imgsz": IMGSZ,
                    "retina_masks": RETINA_MASKS
                }
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

def _parse_s3_event(event):
    """eventからS3のバケット名とキーを抽出する"""
    if "s3_url" in event:
        parsed = urlparse(event["s3_url"])
        return parsed.netloc, parsed.path.lstrip('/')
    
    # 直接指定の場合
    bucket = event.get("bucket")
    key = event.get("key")
    if bucket and key:
        return bucket, key
    
    raise ValueError("Event must contain s3_url or both bucket and key")

def _apply_mask_to_image(original_img, mask_np):
    """マスクを適用して透過PNGを生成"""
    # マスクを元画像サイズにリサイズ
    mask_img = Image.fromarray((mask_np * 255).astype(np.uint8)).resize(original_img.size, resample=Image.BILINEAR)
    
    rgba_img = original_img.copy().convert("RGBA")
    rgba_img.putalpha(mask_img)
    
    buf = io.BytesIO()
    rgba_img.save(buf, format="PNG")
    return buf.getvalue()

def _put_to_s3(buffer, bucket, key):
    """S3にアップロードして署名付きURLを返す"""
    s3.put_object(Bucket=bucket, Key=key, Body=buffer, ContentType="image/png")
    
    # 署名付きURLの生成 (1時間有効)
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600
    )
    return url