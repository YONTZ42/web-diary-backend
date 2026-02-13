
import base64
import json
import os
import io
import boto3
import numpy as np
from PIL import Image

# ultralytics
from ultralytics import YOLO

s3 = boto3.client("s3")

# ---- Env ----
S3_PREFIX = os.environ.get("S3_PREFIX", "cutouts/")
PRESIGN_EXPIRES = int(os.environ.get("PRESIGN_EXPIRES", "3600"))
YOLO_CONFIG_DIR= os.environ.get("YOLO_CONFIG_DIR", "/temp/Ultralytics")  # モデル配置ディレクトリ

# yolo26n-seg.pt / yolo26s-seg.pt ... など（デフォルトは軽量nano）
MODEL_NAME = os.environ.get("MODEL_NAME", "yolo26n-seg.pt")
MODEL_PATH = os.path.join(os.environ.get("LAMBDA_TASK_ROOT", "/var/task"), MODEL_NAME)
model = YOLO(MODEL_PATH)
DEFAULT_BUCKET = os.environ.get("BUCKET_NAME", "")


def _read_request_bytes(event) -> tuple[bytes, str | None]:
    """
    Lambda Proxy eventから画像bytesを取り出す。
    - 生バイナリ（proxyで isBase64Encoded=true の body）
    - もしくは application/json で { "imageBase64": "...", "s3Key": "...", "bucket": "..." } 形式
    """
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    content_type = headers.get("content-type", "")

    body = event.get("body") or ""
    is_b64 = bool(event.get("isBase64Encoded"))

    # JSONで来た場合
    if "application/json" in content_type:
        payload = json.loads(body)
        image_b64 = payload.get("imageBase64")
        if not image_b64:
            raise ValueError("Missing imageBase64 in JSON body")
        return base64.b64decode(image_b64), payload.get("s3Key")

    # バイナリで来た場合（Lambda proxyはbodyをbase64にして渡してくることが多い）
    if is_b64:
        return base64.b64decode(body), (headers.get("x-s3-key") or None)

    # isBase64Encoded=false で生文字列が来たケース（ほぼ無いが保険）
    return body.encode("utf-8"), (headers.get("x-s3-key") or None)


def _segment_to_rgba_png(image_bytes: bytes) -> bytes:
    """
    YOLO segmentationでマスクを作り、背景透過PNG(bytes)を返す。
    ここでは「最も面積が大きいマスク」を採用（複数なら合成も可能）。
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    np_img = np.array(img)

    # 推論（CPU想定）
    results = model(np_img, verbose=False)
    r0 = results[0]

    if r0.masks is None or r0.boxes is None or len(r0.boxes) == 0:
        # 何も検出できない場合：そのまま不透明で返すか、全透明で返すか選べる
        # ここでは「そのまま(不透明)」で返す
        rgba = img.convert("RGBA")
        out = io.BytesIO()
        rgba.save(out, format="PNG")
        return out.getvalue()

    # mask: (n, mask_h, mask_w) float tensor -> numpy
    masks = r0.masks.data.cpu().numpy()  # shape: (N, mh, mw)
    # スコア
    scores = r0.boxes.conf.cpu().numpy()  # (N,)

    # マスクを元画像サイズにリサイズして、最大面積（or スコア最大）を選ぶ
    best_idx = int(np.argmax(scores))
    best_mask = masks[best_idx]

    mask_img = Image.fromarray((best_mask * 255).astype(np.uint8), mode="L")
    mask_img = mask_img.resize((w, h), resample=Image.BILINEAR)

    # しきい値で2値化（必要なら）
    alpha = np.array(mask_img)
    print("Mask alpha stats:", alpha.min(), alpha.max(), alpha.mean())
    alpha = (alpha > 128).astype(np.uint8) * 255
    

    rgba = Image.fromarray(np.dstack([np_img, alpha]), mode="RGBA")

    out = io.BytesIO()
    rgba.save(out, format="PNG")
    return out.getvalue()


def _put_to_s3(png_bytes: bytes, bucket: str, key: str) -> str:
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=png_bytes,
        ContentType="image/png",
        CacheControl="public, max-age=31536000",
    )
    # 返すURLは2択：
    # 1) 署名付きURL（安全・確実）
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=3600,
    )
    return url


def lambda_handler(event, context):
    try:
        img_bytes, s3_key = _read_request_bytes(event)

        # JSONでbucketが来る可能性も考慮
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        bucket = headers.get("x-s3-bucket") or DEFAULT_BUCKET

        out_png = _segment_to_rgba_png(img_bytes)

        s3_url = None
        if s3_key:
            if not bucket:
                raise ValueError("s3Key was provided but BUCKET_NAME or x-s3-bucket is missing")
            s3_url = _put_to_s3(out_png, bucket, s3_key)

        # バイナリ(PNG)で返す：bodyはbase64
        resp_headers = {
            "Content-Type": "image/png",
            "Cache-Control": "no-store",
        }
        # S3 URLも返したい → ヘッダーに載せる（バイナリレスポンスと両立しやすい）
        if s3_url:
            resp_headers["X-S3-URL"] = s3_url
            resp_headers["X-S3-Key"] = s3_key

        return {
            "statusCode": 200,
            "isBase64Encoded": True,
            "headers": resp_headers,
            "body": base64.b64encode(out_png).decode("utf-8"),
        }

    except Exception as e:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)}),
        }
