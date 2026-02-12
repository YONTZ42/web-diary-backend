FROM public.ecr.aws/lambda/python:3.10

# 1. 必要なパッケージをまとめてインストール（NumPyを1.26.4に固定）
RUN python -m pip install -U pip setuptools wheel && \
    python -m pip install --no-cache-dir \
    "numba<0.60" \
    "numpy==1.26.4" \
    "onnxruntime==1.16.3" \
    "rembg==2.0.60"

# 2. requirements.txt がある場合はここで（既存のnumpy等を上書きしないよう注意）
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# 3. ★重要：モデルファイルをビルド時にダウンロードして格納
# Lambda実行時にネットから落とさないようにし、読み取り専用エラーを回避
RUN mkdir -p /var/task/models
ENV U2NET_HOME=/var/task/models
ENV NUMBA_CACHE_DIR=/tmp
ENV MPLCONFIGDIR=/tmp
#ENV NUMBA_DISABLE_JIT=1
# ここで使うモデルをあらかじめダウンロード（例：u2net）
RUN curl -L https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx -o /var/task/models/u2net.onnx

# アプリケーションコード
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]