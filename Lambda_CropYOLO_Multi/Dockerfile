# --- Stage 1: Builder ---
FROM public.ecr.aws/lambda/python:3.11 AS builder

# 必須：バイナリのみの使用を強制し、コンパイルを回避する
ENV PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all: \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN yum -y update && yum -y install libgomp && yum clean all
RUN pip install --upgrade pip

WORKDIR /build
RUN mkdir -p /build/package

# 1. まず numpy を先にバイナリでインストール（依存関係の衝突を防ぐ）
RUN pip install numpy --target /build/package

# 2. requirements.txt のインストール
COPY requirements.txt .
RUN pip install -r requirements.txt --target /build/package

# 3. PyTorch をインストール（--only-binary を念押しで追加）
RUN pip install --no-cache-dir --only-binary=:all: \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 torchvision==0.20.1 --target /build/package

# 4. ultralytics
RUN pip install ultralytics --no-deps --target /build/package

# --- Stage 2: Runtime (変更なし) ---
FROM public.ecr.aws/lambda/python:3.11
RUN yum -y install libgomp && yum clean all
WORKDIR ${LAMBDA_TASK_ROOT}
COPY --from=builder /build/package/ ./
COPY models/yolo26n-seg.pt ./
COPY models/yolo26s-seg.pt ./
COPY lambda_function.py ./
CMD ["lambda_function.lambda_handler"]