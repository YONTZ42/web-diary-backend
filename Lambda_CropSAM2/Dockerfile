FROM public.ecr.aws/lambda/python:3.11

# OS パッケージのインストール
RUN yum update -y && yum install -y \
    gcc gcc-c++ cmake git mesa-libGL \
    && yum clean all

# 1. pip 自体のアップグレード
RUN python -m pip install --upgrade pip

# 2. PyTorch (CPU) のインストール
RUN pip install --no-cache-dir \
    "torch>=2.3.1+cpu" "torchvision>=0.18.1+cpu" \
    --index-url https://download.pytorch.org/whl/cpu

# 3. SAM2 本体のインストール
RUN pip install --no-cache-dir git+https://github.com/facebookresearch/segment-anything-2.git

# 4. 依存関係の地獄を回避するための厳格なインストール
# numpy < 2.0.0 を維持するため、opencv は 4.9.x 以前に固定します
RUN pip install --no-cache-dir \
    "numpy<2.0.0" \
    "opencv-python-headless<4.10" \
    "pillow" \
    "requests" \
    "boto3" \
    "pyyaml"

# 5. モデル重みのダウンロード
RUN mkdir -p /var/task/models && \
    curl -L https://dl.fbaipublicfiles.com/segment_anything_2/072424/sam2_hiera_small.pt \
    -o /var/task/models/sam2_hiera_small.pt

COPY lambda_function.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_function.lambda_handler"]