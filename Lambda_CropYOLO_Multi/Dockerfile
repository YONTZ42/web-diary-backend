# --- Stage 1: Builder (ライブラリのビルド・インストール) ---
FROM public.ecr.aws/lambda/python:3.11 AS builder

# [cite_start]実行に必要なシステムライブラリのインストール [cite: 1]
RUN yum -y update && yum -y install libgomp && yum clean all
RUN pip install --upgrade pip

# 依存ライブラリのインストール先を固定
WORKDIR /build

# [cite_start]requirements.txt の処理 [cite: 2]
COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt --target /build/package

# [cite_start]ultralytics と PyTorch (CPU版) のインストール [cite: 2]
RUN pip install ultralytics --no-deps --target /build/package
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 torchvision==0.20.1 --target /build/package

# --- Stage 2: Runtime (実行用イメージ) ---
FROM public.ecr.aws/lambda/python:3.11

# [cite_start]実行に必要な libgomp をインストール [cite: 1]
RUN yum -y install libgomp && yum clean all

# Builder ステージからインストール済みパッケージをコピー
COPY --from=builder /build/package/ ${LAMBDA_TASK_ROOT}/

# [cite_start]環境変数の設定 [cite: 3]
ENV MODEL_NAME=yolo26n-seg.pt \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    PYTHONUNBUFFERED=1

# [cite_start]モデルファイルとアプリケーションコードのコピー [cite: 3]
COPY models/yolo26n-seg.pt ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
COPY models/yolo26s-seg.pt ${LAMBDA_TASK_ROOT}/yolo26s-seg.pt
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]