FROM public.ecr.aws/lambda/python:3.11

# OS パッケージのインストール
RUN yum update -y && yum install -y \
    gcc gcc-c++ cmake git mesa-libGL \
    && yum clean all

# 1. pip 自体のアップグレード
RUN python -m pip install --upgrade pip

RUN pip install --no-cache-dir "numpy<2.0.0"

# 2. PyTorch (CPU) のインストール
# "+cpu" を使う場合は必ず "==" を使用します
RUN pip install --no-cache-dir \
    "torch==2.3.1+cpu" \
    "torchvision==0.18.1+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# 3. SAM2 本体のインストール
#RUN pip install --no-cache-dir "sam-2==1.0" #numpy version2.0問題回避のためコメントアウト
RUN pip install --no-cache-dir "git+https://github.com/facebookresearch/segment-anything-2.git"

# 4. 依存関係の競合（NumPy 2.0 問題）を回避
# OpenCV 4.10以降はNumPy 2.0を要求し、ビルドエラー（GCCの古さ）を引き起こすため固定
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

# 手順1: 基礎となる NumPy 1.x を先に固定して入れる
RUN pip install --no-cache-dir "numpy==1.26.4"

# 手順2: PyTorch と Torchvision を CPU 版で入れる
# ここで --extra-index-url を使い、NumPy が PyPI から 1.x のまま維持されるようにする
RUN pip install --no-cache-dir \
    "torch==2.3.1+cpu" \
    "torchvision==0.18.1+cpu" \
    --extra-index-url https://download.pytorch.org/whl/cpu

# 手順3: OpenCV を「NumPy 2.0 を要求しない古い版」に固定する
RUN pip install --no-cache-dir "opencv-python-headless==4.9.0.80"

# 手順4: SAM2 を入れる
RUN pip install --no-cache-dir "sam-2==1.0"