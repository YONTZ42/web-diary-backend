FROM public.ecr.aws/lambda/python:3.11

# システムライブラリのインストール (OpenCV等の依存関係)
RUN yum install -y mesa-libGL

# 作業ディレクトリの設定
WORKDIR ${LAMBDA_TASK_ROOT}

# Pythonライブラリのインストール
# rembg[gpu] ではなく通常の rembg (CPU版) を使用 (Lambdaは通常GPUなしのため)
RUN pip install --no-cache-dir \
    rembg \
    onnxruntime \
    boto3 \
    requests \
    numpy \
    Pillow

# モデルファイルの事前ロード設定
# rembg は $U2NET_HOME/.u2net/ にモデルを探しに行く
ENV U2NET_HOME=${LAMBDA_TASK_ROOT}
RUN mkdir -p ${LAMBDA_TASK_ROOT}/.u2net

# ビルド時にモデルをダウンロードしておく (isnet-general-use)
# これにより実行時のインターネットアクセスと遅延を防ぐ
RUN curl -L https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx \
    -o ${LAMBDA_TASK_ROOT}/.u2net/isnet-general-use.onnx

# コードのコピー
COPY lambda_function.py .

# ハンドラの設定
CMD [ "lambda_function.lambda_handler" ]