# --- ステージ1: ビルド (builder) ---
FROM public.ecr.aws/lambda/python:3.12 AS builder
WORKDIR /build
COPY requirements.txt .
# すべての依存関係（google-genai, pydantic, httpx等）を一括インストール
RUN pip install --no-cache-dir -r requirements.txt --target /build/package

# --- ステージ2: 実行 (runtime) ---
FROM public.ecr.aws/lambda/python:3.12
WORKDIR ${LAMBDA_TASK_ROOT}
# builderからインストール済みモジュールをコピー
COPY --from=builder /build/package/ .
# 最新の app.py をコピー
COPY app.py .

# .pycを生成してインポートを高速化
ENV PYTHONDONTWRITEBYTECODE=0 \
    PYTHONUNBUFFERED=1

CMD [ "app.handler" ]