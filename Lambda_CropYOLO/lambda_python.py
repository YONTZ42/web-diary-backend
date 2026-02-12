import os
import io
import json
import uuid
import time
from urllib.parse import urlparse

import boto3
import requests
from PIL import Image
import numpy as np

from ultralytics import YOLO

# ---- Env ----
S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "cutouts/")
PRESIGN_EXPIRES = int(os.environ.get("PRESIGN_EXPIRES", "3600"))

# yolo26n-seg.pt / yolo26s-seg.pt ... など（デフォルトは軽量nano）
MODEL_NAME = os.environ.get("MODEL_NAME", "yolo26n-seg.pt")

# ---- Clients / Model (cold startでロード) ----
s3 = boto3.client("s3")
model = YOLO(MODEL_NAME)


def _download_image(url: str, timeout=15) -> Image.Image:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    return img


def _pick_most_salient_instance(result) -> int:
    """
    「最も目立つ」= (mask area) * (confidence) が最大のインスタンスを選ぶ
    """
    if result.masks is None or result.boxes is None:
        raise ValueError("No masks/boxes found")

    masks = result.masks.data  # torch.Tensor [N, H, W]
    conf = result.boxes.conf   # torch.Tensor [N]

    # mask area
    areas = masks.sum(dim=(1, 2)).float()  # [N]
    scores = areas * conf.float()
    idx = int(scores.argmax().item())
    return idx


def _make_rgba_cutout(img_rgb: Image.Image, mask_2d: np.ndarray) -> Image.Image:
    """
    mask_2d: (H,W) boolean or 0..1 float
    """
    if mask_2d.dtype != np.uint8:
        mask_u8 = (mask_2d > 0.5).astype(np.uint8) * 255
    else:
        mask_u8 = mask_2d

    rgba = img_rgb.convert("RGBA")
    alpha = Image.fromarray(mask_u8, mode="L")
    rgba.putalpha(alpha)
    return rgba


def lambda_handler(event, context):
    """
    event:
      {
        "image_url": "https://....jpg",
        "key": "optional/path/output.png",   # optional
        "return": "presigned" | "s3"         # optional (default presigned)
      }
    """
    try:
        image_url = event["image_url"]
        out_key = event.get("key")
        return_mode = event.get("return", "presigned")

        if not out_key:
            out_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"

        # 1) download
        img = _download_image(image_url)

        # 2) infer
        # imgsz: 小さくすると高速/精度↓。必要なら env で調整してもOK
        results = model.predict(img, verbose=False)
        r0 = results[0]

        # 3) choose instance
        idx = _pick_most_salient_instance(r0)

        # 4) mask -> numpy
        # masks.data is torch; convert to numpy
        mask = r0.masks.data[idx].cpu().numpy()  # (H,W) float/bool

        # 5) create cutout
        cutout = _make_rgba_cutout(img, mask)

        # 6) save to /tmp
        tmp_path = f"/tmp/{uuid.uuid4().hex}.png"
        cutout.save(tmp_path, format="PNG", optimize=True)

        # 7) upload to s3
        with open(tmp_path, "rb") as f:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=out_key,
                Body=f,
                ContentType="image/png",
                CacheControl="public, max-age=31536000, immutable",
            )

        # 8) return url
        if return_mode == "s3":
            url = f"s3://{S3_BUCKET}/{out_key}"
        else:
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": S3_BUCKET, "Key": out_key},
                ExpiresIn=PRESIGN_EXPIRES,
            )

        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps(
                {"bucket": S3_BUCKET, "key": out_key, "url": url},
                ensure_ascii=False
            ),
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": str(e)}, ensure_ascii=False),
        }
