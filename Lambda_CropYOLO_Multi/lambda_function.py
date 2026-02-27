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
S3_PREFIX = os.environ.get("S3_PREFIX", "masks/")

# YOLO推論パラメータ (環境変数で変更可能)
CONF_THRES = float(os.environ.get("CONF_THRESHOLD", "0.25"))
IOU_THRES = float(os.environ.get("IOU_THRESHOLD", "0.45"))
MAX_DET = int(os.environ.get("MAX_DET", "10"))
IMGSZ = int(os.environ.get("IMGSZ", "640"))
RETINA_MASKS = os.environ.get("RETINA_MASKS", "true").lower() == "true"

# モデルのロード
MODEL_PATH = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", "/var/task"), MODEL_NAME)
model = YOLO(MODEL_PATH)

def lambda_handler(event, context):
    # 1. 起動確認用フラグのチェック
    if event.get("only_for_boot"):
        return {
            "statusCode": 200,
            "body": json.dumps("Hello, I am YOLO!")
        }

    try:
        # 2. S3URLから画像をダウンロード
        bucket, key = _parse_s3_event(event)
        response = s3.get_object(Bucket=bucket, Key=key)
        img_bytes = response['Body'].read()
        img = Image.open(io.BytesIO(img_bytes))
        orig_size = img.size # オリジナル画像サイズ (W, H)
        
        # 3. YOLO推論
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

        # 4. マスクデータの画像化と保存
        if hasattr(result, 'masks') and result.masks is not None:
            # result.masks.data は [N, H, W] のテンソル
            for mask_tensor in result.masks.data:
                # 0.0-1.0の値を0 or 255の白黒画像(Lモード)に変換
                mask_np = (mask_tensor.cpu().numpy() * 255).astype(np.uint8)
                
                # 推論サイズからオリジナル画像サイズへリサイズ
                mask_img = Image.fromarray(mask_np).resize(orig_size, resample=Image.NEAREST)
                
                # バイト列に変換 (透過なしのLモードなので非常に軽量)
                buf = io.BytesIO()
                mask_img.save(buf, format="PNG")
                mask_bytes = buf.getvalue()
                
                # S3に保存
                dest_bucket = DEFAULT_BUCKET or bucket
                dest_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"
                
                url = _put_to_s3(mask_bytes, dest_bucket, dest_key)
                mask_urls.append(url)

        # 5. レスポンス
        return {
            "statusCode": 200,
            "body": json.dumps({
                "detected_count": len(mask_urls),
                "mask_urls": mask_urls,
                "parameters": {
                    "imgsz": IMGSZ,
                    "retina_masks": RETINA_MASKS,
                    "max_det": MAX_DET
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
    if "s3_url" in event:
        parsed = urlparse(event["s3_url"])
        return parsed.netloc, parsed.path.lstrip('/')
    bucket, key = event.get("bucket"), event.get("key")
    if bucket and key: return bucket, key
    raise ValueError("Missing s3_url or bucket/key")

def _put_to_s3(buffer, bucket, key):
    s3.put_object(Bucket=bucket, Key=key, Body=buffer, ContentType="image/png")
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600
    )