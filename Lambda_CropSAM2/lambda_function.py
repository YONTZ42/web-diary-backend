import os
import io
import json
import uuid
import logging
from typing import Any, Dict, Tuple

import boto3
import numpy as np
import requests
from PIL import Image

import torch
from sam2.build_sam import build_sam2
from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client("s3")

# ---- モデル設定（SAM 2.1 tiny を前提）----
MODEL_DIR = os.environ.get("SAM2_MODEL_DIR", "/opt/sam2_checkpoints")
CHECKPOINT_PATH = os.path.join(MODEL_DIR, "sam2.1_hiera_tiny.pt")
MODEL_CFG = os.environ.get("SAM2_MODEL_CFG", "configs/sam2.1/sam2.1_hiera_t.yaml")

# S3 出力先デフォルト（envで指定推奨）
DEFAULT_BUCKET = os.environ.get("OUTPUT_BUCKET", "")
DEFAULT_PREFIX = os.environ.get("OUTPUT_PREFIX", "cutouts/")


# グローバルにロード（コールドスタートでのみ）
_model = None
_mask_generator = None


def _load_model():
    global _model, _mask_generator
    if _mask_generator is not None:
        return

    if not os.path.exists(CHECKPOINT_PATH):
        raise FileNotFoundError(f"Checkpoint not found: {CHECKPOINT_PATH}")

    device = "cpu"
    torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "2")))

    # CPU運用なので postprocessing は無効でもOK（CUDA拡張なしでも動く想定）
    _model = build_sam2(
        model_cfg=MODEL_CFG,
        checkpoint=CHECKPOINT_PATH,
        device=device,
        apply_postprocessing=False,
    )
    _mask_generator = SAM2AutomaticMaskGenerator(_model)
    logger.info("SAM2 model loaded (CPU).")


def _fetch_image(image_url: str, timeout_sec: int = 15) -> Image.Image:
    headers = {"User-Agent": "lambda-sam2-cutout/1.0"}
    r = requests.get(image_url, headers=headers, timeout=timeout_sec)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGB")
    return img


def _pick_largest_mask(masks: list) -> np.ndarray:
    """
    SAM2AutomaticMaskGeneratorの返り値（list[dict]）から最大領域を選ぶ。
    dictには通常 'segmentation' (H,W bool) と 'area' が含まれる想定。
    """
    if not masks:
        raise ValueError("No masks generated. Try another image or increase memory/timeout.")

    # area が無い実装差分に備えて fallback
    def area_of(m):
        if "area" in m:
            return m["area"]
        seg = m.get("segmentation")
        return int(np.sum(seg)) if seg is not None else 0

    largest = max(masks, key=area_of)
    seg = largest.get("segmentation")
    if seg is None:
        raise ValueError("Mask dict missing 'segmentation'.")
    return seg.astype(np.uint8)  # 0/1


def _apply_alpha_cutout(img_rgb: Image.Image, mask01: np.ndarray) -> Image.Image:
    """
    RGB画像 + 0/1マスク -> RGBA(背景透過) PNG用
    """
    w, h = img_rgb.size
    if mask01.shape[0] != h or mask01.shape[1] != w:
        # SAM2側のサイズが合わないケースに備え、最近傍で合わせる
        mask_img = Image.fromarray((mask01 * 255).astype(np.uint8), mode="L").resize((w, h), Image.NEAREST)
        alpha = np.array(mask_img, dtype=np.uint8)
    else:
        alpha = (mask01 * 255).astype(np.uint8)

    rgba = img_rgb.convert("RGBA")
    rgba_np = np.array(rgba, dtype=np.uint8)
    rgba_np[:, :, 3] = alpha
    return Image.fromarray(rgba_np, mode="RGBA")


def _put_png_to_s3(img_rgba: Image.Image, bucket: str, key: str) -> str:
    buf = io.BytesIO()
    img_rgba.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue(),
        ContentType="image/png",
        CacheControl="public, max-age=31536000, immutable",
    )
    return f"s3://{bucket}/{key}"


def _presign_get_url(bucket: str, key: str, expires: int = 3600) -> str:
    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    event example:
    {
      "image_url": "https://example.com/cat.jpg",
      "bucket": "your-output-bucket",
      "prefix": "cutouts/",
      "return_presigned": true
    }
    """
    try:
        _load_model()

        image_url = event.get("image_url")
        if not image_url:
            return {"statusCode": 400, "body": json.dumps({"error": "image_url is required"})}

        bucket = event.get("bucket") or DEFAULT_BUCKET
        if not bucket:
            return {"statusCode": 400, "body": json.dumps({"error": "bucket is required (or set OUTPUT_BUCKET env)"})}

        prefix = event.get("prefix") or DEFAULT_PREFIX
        prefix = prefix if prefix.endswith("/") else prefix + "/"

        return_presigned = bool(event.get("return_presigned", False))
        presign_expires = int(event.get("presign_expires", 3600))

        # 1) fetch image
        img = _fetch_image(image_url)

        # 2) generate masks (automatic)
        img_np = np.array(img)  # RGB uint8
        with torch.inference_mode():
            masks = _mask_generator.generate(img_np)

        # 3) choose the largest object
        largest_mask = _pick_largest_mask(masks)

        # 4) apply alpha cutout
        cutout = _apply_alpha_cutout(img, largest_mask)

        # 5) upload to S3
        out_key = f"{prefix}{uuid.uuid4().hex}.png"
        s3_url = _put_png_to_s3(cutout, bucket, out_key)

        resp = {"s3_url": s3_url, "bucket": bucket, "key": out_key}

        if return_presigned:
            resp["presigned_url"] = _presign_get_url(bucket, out_key, expires=presign_expires)

        return {"statusCode": 200, "body": json.dumps(resp)}

    except Exception as e:
        logger.exception("Failed")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
