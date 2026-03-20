import os
import json
import uuid
import base64
import logging
from datetime import datetime
import time

import boto3
import httpx
from google import genai
from google.genai import types

# ロギング設定
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def _log(level: str, message: str, **fields):
    payload = {
        "message": message,
        "service": os.environ.get("SERVICE_NAME", "mini-museum-gen-image"),
        "stage": os.environ.get("STAGE", os.environ.get("APP_ENV", "local")),
        "component": "lambda.app",
        **fields,
    }
    getattr(logger, level.lower())(json.dumps(payload, ensure_ascii=False))


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
    started_at = time.perf_counter()
    aws_request_id = getattr(context, "aws_request_id", None)

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
                _log(
                    "error",
                    "invalid json body",
                    event="request_failed",
                    error_code="INVALID_JSON_BODY",
                    aws_request_id=aws_request_id,
                    status_code=400,
                )
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
        input_source = "image_data" if image_data_raw else "image_url" if image_url else "text_only"

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
            _log(
                "info",
                "decoded input image_data",
                event="image_decode_succeeded",
                aws_request_id=aws_request_id,
                input_source=input_source,
                source_image_size_bytes=len(image_bytes),
            )
            contents.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/jpeg" # 入力がpngでもjpeg扱いで通るケースが多いが、必要ならheaderから判定
                )
            )
        elif image_url:
            # URLから画像をダウンロード
            _log(
                "info",
                "fetching input image from url",
                event="image_fetch_started",
                aws_request_id=aws_request_id,
                input_source=input_source,
                image_url=image_url,
            )
            resp = httpx.get(image_url, timeout=10.0)
            resp.raise_for_status()
            _log(
                "info",
                "fetched input image from url",
                event="image_fetch_succeeded",
                aws_request_id=aws_request_id,
                input_source=input_source,
                image_url=image_url,
                source_image_size_bytes=len(resp.content),
            )
  
            contents.append(
                types.Part.from_bytes(
                    data=resp.content,
                    mime_type=resp.headers.get('Content-Type', 'image/jpeg')
                )
            )

        # ---------------------------------------------------------
        # 4. Geminiによる画像生成
        # ---------------------------------------------------------
        _log(
            "info",
            "generating image content",
            event="generation_started",
            aws_request_id=aws_request_id,
            model_name=MODEL_NAME,
            input_source=input_source,
        )
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


        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _log(
            "info",
            "image generation succeeded",
            event="request_succeeded",
            aws_request_id=aws_request_id,
            model_name=MODEL_NAME,
            input_source=input_source,
            file_key=file_key,
            duration_ms=duration_ms,
            status_code=200,
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'url': final_url,
                'file_key': file_key
            })
        }

    except Exception as e:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        _log(
            "error",
            "image generation failed",
            event="request_failed",
            aws_request_id=aws_request_id,
            error_type=type(e).__name__,
            error_code="GEN_IMAGE_FAILED",
            duration_ms=duration_ms,
            status_code=500,
        )
        logger.exception("Unhandled exception in app.handler")


        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': str(e)})
        }

        