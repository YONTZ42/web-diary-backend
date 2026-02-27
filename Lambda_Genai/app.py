import os
import json
import uuid
import base64
import logging
from datetime import datetime

import boto3
import httpx
from google import genai
from google.genai import types

# ロギング設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# --- グローバル初期化 (Cold Start対策) ---
API_KEY = os.environ.get('GOOGLE_API_KEY')
# 最新SDKのクライアント初期化
client = genai.Client(api_key=API_KEY) if API_KEY else None

s3 = boto3.client('s3')
BUCKET_NAME = os.environ.get('DEST_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')

# 環境変数からの生成設定
MODEL_NAME = os.environ.get('MODEL_NAME', 'gemini-2.0-flash') # 画像生成対応モデルを指定
DEFAULT_PROMPT = os.environ.get('DEFAULT_PROMPT', 'A professional 3D acrylic block photography')
OUTPUT_MIME_TYPE = os.environ.get('OUTPUT_MIME_TYPE', 'image/png')
ASPECT_RATIO = os.environ.get('ASPECT_RATIO', '1:1')

def handler(event, context):
    try:
        if not client:
            raise Exception("Google API Key is not configured.")

        # 1. 入力パラメータのパース
        user_prompt = event.get('prompt', '')
        image_url = event.get('image_url')
        image_data_b64 = event.get('image_data')

        # 2. コンテンツの組み立て
        final_prompt = f"{DEFAULT_PROMPT} {user_prompt}".strip()
        contents = [final_prompt]

        # 画像入力がある場合の処理
        if image_data_b64:
            contents.append(
                types.Part.from_bytes(
                    data=base64.b64decode(image_data_b64),
                    mime_type="image/jpeg"
                )
            )
        elif image_url:
            resp = httpx.get(image_url)
            contents.append(
                types.Part.from_bytes(
                    data=resp.content,
                    mime_type=resp.headers.get('Content-Type', 'image/jpeg')
                )
            )

        # 3. 最新の generate_content による画像生成
        # config 内で出力形式を制御
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                # 画像を生成するための最新フラグ（モデルが対応している必要あり）
                response_modalities=["IMAGE"],
                # 必要に応じてアスペクト比などの詳細設定を追加
                # image_config=types.ImageConfig(aspect_ratio=ASPECT_RATIO) 
            )
        )

        # 4. 生成された画像バイナリの抽出
        # response.candidates[0].content.parts から画像のパーツを探す
        image_part = next(p for p in response.candidates[0].content.parts if p.inline_data)
        image_bytes = image_part.inline_data.data

        # 5. S3保存
        ext = "png" if "png" in OUTPUT_MIME_TYPE else "jpg"
        file_key = f"gen/{datetime.now().strftime('%Y%m')}/{uuid.uuid4()}.{ext}"
        
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=file_key,
            Body=image_bytes,
            ContentType=OUTPUT_MIME_TYPE,
            CacheControl='max-age=31536000'
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'url': f"https://{CLOUDFRONT_DOMAIN}/{file_key}",
                'file_key': file_key
            })
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': str(e)})
        }