# --- Stage 1: Builder ---
FROM public.ecr.aws/lambda/python:3.11 AS builder

ENV PIP_NO_CACHE_DIR=1

# ビルドに必要な最小限のライブラリ（onnxruntime や opencv のビルド等に備える）
RUN yum -y update && yum -y install gcc-c++ && yum clean all

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefer-binary -r requirements.txt

# モデルの事前ダウンロード (isnet-general-use)
# rembg は $U2NET_HOME/.u2net/ モデル名.onnx を探しに行く
RUN mkdir -p /build/models/.u2net && \
    curl -L https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-anime.onnx \
    -o /build/models/.u2net/isnet-anime.onnx    
# --- Stage 2: Runtime ---
FROM public.ecr.aws/lambda/python:3.11

# 実行に必要な最小限のランタイムライブラリ (libGLはopencv用)
RUN yum -y install mesa-libGL && yum clean all

# Builder ステージから Python パッケージをコピー
COPY --from=builder /var/lang/lib/python3.11/site-packages/ /var/lang/lib/python3.11/site-packages/

# モデルファイルをコピー
COPY --from=builder /build/models/.u2net /var/task/.u2net

WORKDIR ${LAMBDA_TASK_ROOT}


# コードをコピー
COPY lambda_function.py .

# --- キャッシュ作成のためのダミー実行 ---
# 1. Lambda実行時と同じように /tmp/.u2net を作成し、モデルへのリンクを張る
# 2. PYTHONPATH を設定し、モデルをロードするスクリプトを実行する
RUN mkdir -p /tmp/.u2net && \
    ln -s /var/task/.u2net/* /tmp/.u2net/ && \
    export PYTHONPATH=${LAMBDA_TASK_ROOT} && \
    export U2NET_HOME=/tmp/.u2net && \
    python3 -c "from rembg import new_session; new_session('isnet-anime')" && \
    rm -rf /tmp/.u2net


CMD ["lambda_function.lambda_handler"]