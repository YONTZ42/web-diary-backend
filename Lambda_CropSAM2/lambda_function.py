import os
import io
import json
import boto3
import torch
import numpy as np
import requests
from PIL import Image
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

# 環境変数（S3バケット名などはLambda側で設定）
S3_BUCKET = os.environ.get("OUTPUT_BUCKET")
MODEL_PATH = "/var/task/models/sam2_hiera_small.pt"
MODEL_CONFIG = "sam2_hiera_s.yaml" # ライブラリ内蔵のconfig名

# モデルのグローバルロード（コールドスタート対策）
device = torch.device("cpu")
sam2_model = build_sam2(MODEL_CONFIG, MODEL_PATH, device=device)
predictor = SAM2ImagePredictor(sam2_model)

s3 = boto3.client("s3")

def lambda_handler(event, context):
    try:
        
        greeting = event.get("greeting", None)
        if isinstance(greeting, str) and greeting.strip():
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "Hello, Stkcker Geek!", "received": greeting})
            }
        
        # 1. パラメータ取得
        image_url = event.get("image_url")
        if not image_url:
            return {"statusCode": 400, "body": "No image_url provided"}

        # 2. 画像のダウンロード
        response = requests.get(image_url)
        image = Image.open(io.BytesIO(response.content)).convert("RGB")
        image_np = np.array(image)

        # 3. SAM2 による推論
        predictor.set_image(image_np)
        
        # プロンプト設定：とりあえず画像の中央を指定（物体が中央にある想定）
        input_point = np.array([[image_np.shape[1] // 2, image_np.shape[0] // 2]])
        input_label = np.array([1]) # 1は「その点を含む物体」

        masks, scores, logits = predictor.predict(
            point_coords=input_point,
            point_labels=input_label,
            multimask_output=False,
        )

        # 4. 切り抜き処理（背景を透明化）
        mask = masks[0]
        # RGBA画像を作成
        result_img = Image.new("RGBA", image.size, (0, 0, 0, 0))
        result_img.paste(image, (0, 0), mask=Image.fromarray((mask * 255).astype(np.uint8)))

        # 5. S3へアップロード
        output_key = f"output/{context.aws_request_id}.png"
        buffer = io.BytesIO()
        result_img.save(buffer, format="PNG")
        buffer.seek(0)

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=output_key,
            Body=buffer,
            ContentType="image/png"
        )

        # 6. URLの返却（署名付きURLまたはパブリックURL）
        res_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{output_key}"

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "success",
                "s3_url": res_url
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}