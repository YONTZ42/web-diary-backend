import json
import os
import io
import boto3
import base64
import requests
import uuid
import shutil
from PIL import Image
import glob

s3 = boto3.client("s3")


os.environ["U2NET_HOME"] = "/tmp"
os.environ["NUMBA_CACHE_DIR"] = "/tmp/numba_cache"
os.environ["NUMBA_NUM_THREADS"] = "1"

print(f"Current U2NET_HOME: {os.environ.get('U2NET_HOME')}")
print(f"Check files: {glob.glob('/var/task/.u2net/*')}")


# モデルファイルを /var/task/.u2net から /tmp/.u2net へコピー
# これにより pooch が /tmp 内で自由に管理ファイルを作成できるようになります
source_dir = "/var/task/.u2net"
target_dir = "/tmp/.u2net"

if not os.path.exists(target_dir):
    os.makedirs(target_dir, exist_ok=True)
    for item in os.listdir(source_dir):
        s = os.path.join(source_dir, item)
        d = os.path.join(target_dir, item)
        if not os.path.exists(d):
            # シンボリックリンクで十分な場合が多いですが、権限エラー回避にはコピーが確実
            try:
                os.symlink(s, d)
            except OSError:
                shutil.copy2(s, d)
# ---- 環境変数から設定を取得 ----
MODEL_NAME = os.environ.get("MODEL_NAME", "isnet-general-use")
DEFAULT_BUCKET = os.environ.get("BUCKET_NAME", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "removed_bg/")

# rembgパラメータ
ALPHA_MATTING = os.environ.get("ALPHA_MATTING", "false").lower() == "true"
ALPHA_MATTING_FOREGROUND_THRESHOLD = int(os.environ.get("AM_FG_THRESHOLD", "240"))
ALPHA_MATTING_BACKGROUND_THRESHOLD = int(os.environ.get("AM_BG_THRESHOLD", "10"))
ALPHA_MATTING_ERODE_SIZE = int(os.environ.get("AM_ERODE_SIZE", "10"))

from rembg import remove, new_session
# セッションの初期化（初回起動時にモデルがロードされる）
session = new_session(
    model_name=MODEL_NAME,
    providers=['CPUExecutionProvider']
    )

def lambda_handler(event, context):
    # 1. パラメータの抽出 (Function URL / API Gateway対応)
    params = event
    if "body" in event and isinstance(event["body"], str):
        try:
            params = json.loads(event["body"])
        except json.JSONDecodeError:
            return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    # 2. 起動確認用
    if params.get("only_for_boot"):
        return {"statusCode": 200, "body": json.dumps("Hello, I am Rembg (IS-Net)!")}

    try:
        # 画像データの取得
        img_bytes = _get_image_data(params)
        
        # 背景除去の実行
        # rembg.remove は bytes を受け取り bytes を返すことが可能
        output_bytes = remove(
            img_bytes,
            session=session,
            alpha_matting=ALPHA_MATTING,
            alpha_matting_foreground_threshold=ALPHA_MATTING_FOREGROUND_THRESHOLD,
            alpha_matting_background_threshold=ALPHA_MATTING_BACKGROUND_THRESHOLD,
            alpha_matting_erode_size=ALPHA_MATTING_ERODE_SIZE
        )

        # S3への保存
        dest_bucket = DEFAULT_BUCKET
        dest_key = f"{S3_PREFIX}{uuid.uuid4().hex}.png"
        
        output_url = _put_to_s3(output_bytes, dest_bucket, dest_key)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "processed_url": output_url
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

def _get_image_data(params):
    if "image_data" in params:
        data_str = params["image_data"]
        if "," in data_str:
            encoded = data_str.split(",", 1)[1]
        else:
            encoded = data_str
        return base64.b64decode(encoded)

    if "image_url" in params:
        res = requests.get(params["image_url"], timeout=10)
        res.raise_for_status()
        return res.content

    bucket = params.get("bucket")
    key = params.get("key")
    if bucket and key:
        response = s3.get_object(Bucket=bucket, Key=key)
        return response['Body'].read()

    raise ValueError("No valid image source provided.")

def _put_to_s3(buffer, bucket, key):
    if not bucket:
        raise ValueError("Environment variable BUCKET_NAME is not set.")
    
    s3.put_object(Bucket=bucket, Key=key, Body=buffer, ContentType="image/png")
    
    return s3.generate_presigned_url(
        "get_object", 
        Params={"Bucket": bucket, "Key": key}, 
        ExpiresIn=3600
    )