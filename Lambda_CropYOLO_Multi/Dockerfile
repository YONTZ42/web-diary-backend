# --- Stage 1: Builder ---
FROM public.ecr.aws/lambda/python:3.11 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all:

# ビルドに必要な最小限のライブラリ
RUN yum -y update && yum -y install libgomp gcc-c++ && yum clean all

WORKDIR /build

# 1. 依存関係を標準のsite-packages（/var/lang/lib/python3.11/site-packages）にインストール
# --target を使わず、システムのpip環境に直接入れます
RUN pip install --upgrade pip && \
    pip install requests boto3 && \
    pip install numpy && \
    pip install --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1 torchvision==0.20.1 && \
    pip install ultralytics --no-deps

# 2. ★重要：ビルド中に「nms」が動作するかテストする
# ここでエラーが出れば、ビルドが失敗するのでデプロイ前に気付けます
RUN python -c "import torch; import torchvision; print('NMS Check:', torchvision.ops.nms)"

# --- Stage 2: Runtime ---
FROM public.ecr.aws/lambda/python:3.11

# 実行に必要なライブラリ
RUN yum -y install libgomp && yum clean all

# Builder ステージの site-packages から Runtime の site-packages へ丸ごとコピー
# これによりパスの不整合を防ぎます
COPY --from=builder /var/lang/lib/python3.11/site-packages/ /var/lang/lib/python3.11/site-packages/

WORKDIR ${LAMBDA_TASK_ROOT}

# モデルとコードをコピー
COPY models/yolo26n-seg.pt ./
COPY models/yolo26s-seg.pt ./
COPY lambda_function.py ./

CMD ["lambda_function.lambda_handler"]