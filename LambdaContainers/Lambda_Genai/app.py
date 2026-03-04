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
        # ---------------------------------------------------------
        # 1. パラメータの抽出 (Function URL対応)
        # ---------------------------------------------------------
        params = event
        # Function URL経由(bodyがJSON文字列)の場合はパースして params に代入
        if "body" in event and isinstance(event["body"], str):
            try:
                params = json.loads(event["body"])
            except json.JSONDecodeError:
                return {
                    'statusCode': 400, 
                    'body': json.dumps({'success': False, 'error': 'Invalid JSON body'})
                }

        if not client:
            raise Exception("Google API Key is not configured.")

        # ---------------------------------------------------------
        # 2. 入力データの取得
        # ---------------------------------------------------------
        user_prompt = params.get('prompt', '')
        image_url = params.get('image_url')
        image_data_raw = params.get('image_data') # Base64文字列 (header付きの可能性あり)

        # ---------------------------------------------------------
        # 3. コンテンツの組み立て
        # ---------------------------------------------------------
        final_prompt = f"{DEFAULT_PROMPT} {user_prompt}".strip()
        contents = [final_prompt]

        # 画像入力がある場合の処理
        if image_data_raw:
            # "data:image/png;base64," などのヘッダーを除去
            if "," in image_data_raw:
                _, encoded = image_data_raw.split(",", 1)
            else:
                encoded = image_data_raw
            
            image_bytes = base64.b64decode(encoded)
            
            contents.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg" # 入力がpngでもjpeg扱いで通るケースが多いが、必要ならheaderから判定
                )
            )
        elif image_url:
            # URLから画像をダウンロード
            logger.info(f"Fetching image from URL: {image_url}")
            resp = httpx.get(image_url, timeout=10.0)
            resp.raise_for_status()
            
            contents.append(
                types.Part.from_bytes(
                    data=resp.content,
                    mime_type=resp.headers.get('Content-Type', 'image/jpeg')
                )
            )

        # ---------------------------------------------------------
        # 4. Geminiによる画像生成
        # ---------------------------------------------------------
        logger.info(f"Generating content with model: {MODEL_NAME}")
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                # 必要に応じてアスペクト比などの詳細設定を追加
                # image_config=types.ImageConfig(aspect_ratio=ASPECT_RATIO) 
            )
        )

        # ---------------------------------------------------------
        # 5. 生成された画像バイナリの抽出とS3保存
        # ---------------------------------------------------------
        # response.candidates[0].content.parts から画像のパーツを探す
        try:
            image_part = next(p for p in response.candidates[0].content.parts if p.inline_data)
            image_bytes = image_part.inline_data.data
        except StopIteration:
            raise Exception("No image generated in response.")

        # 保存ファイル名の決定
        ext = "png" if "png" in OUTPUT_MIME_TYPE else "jpg"
        file_key = f"gen/{datetime.now().strftime('%Y%m')}/{uuid.uuid4()}.{ext}"
        
        if not BUCKET_NAME:
            raise Exception("DEST_BUCKET_NAME is not configured.")

        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=file_key,
            Body=image_bytes,
            ContentType=OUTPUT_MIME_TYPE,
            CacheControl='max-age=31536000'
        )

        # 最終的なURLの生成
        final_url = f"https://{CLOUDFRONT_DOMAIN}/{file_key}" if CLOUDFRONT_DOMAIN else f"https://{BUCKET_NAME}.s3.amazonaws.com/{file_key}"

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'url': final_url,
                'file_key': file_key
            })
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': str(e)})
        }