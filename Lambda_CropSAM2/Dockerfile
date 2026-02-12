# AWS Lambda Python 3.11 ベースイメージ
FROM public.ecr.aws/lambda/python:3.11

# OS パッケージのインストール（OpenCV や SAM2 のビルドに必要）
RUN yum update -y && yum install -y \
    gcc \
    gcc-c++ \
    cmake \
    git \
    mesa-libGL \
    && yum clean all

# 1. 依存関係のインストール
# SAM2 は torch 2.3.1+ を推奨。CPU版を指定してインストール
RUN pip install --no-cache-dir \
    "numpy<2.0.0" \
    "torch>=2.3.1" \
    "torchvision>=0.18.1" \
    --index-url https://download.pytorch.org/whl/cpu

# 2. SAM2 本体のインストール
RUN pip install --no-cache-dir git+https://github.com/facebookresearch/segment-anything-2.git

# 3. その他の必要ライブラリ
RUN pip install --no-cache-dir \
    opencv-python-headless \
    pillow \
    requests \
    boto3

# 4. モデル重みのダウンロード
# 今回は比較的軽量で高精度な sam2_hiera_small.pt を使用
RUN mkdir -p /var/task/models && \
    curl -L https://dl.fbaipublicfiles.com/segment_anything_2/072424/sam2_hiera_small.pt \
    -o /var/task/models/sam2_hiera_small.pt

# 5. アプリケーションコードのコピー
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# 起動コマンド
CMD ["lambda_function.lambda_handler"]