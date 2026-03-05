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

# rembgがモデルを探す基準ディレクトリを /var/task に指定
ENV NUMBA_CACHE_DIR=/tmp/numba_cache
ENV NUMBA_NUM_THREADS=1

# コードをコピー
COPY lambda_function.py .

CMD ["lambda_function.lambda_handler"]