FROM public.ecr.aws/lambda/python:3.11

# pipを静かに・速く
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all: \
    YOLO_CONFIG_DIR=/tmp/Ultralytics \
    MODEL_NAME=yolo26n-seg.pt

# 依存（ultralytics/torch が libgomp を要求することがある）
RUN yum -y update \
 && yum -y install libgomp \
 && yum clean all

RUN pip install --upgrade pip

# まずrequirements（あるなら）を入れる
# requirements.txt が無いなら、空ファイルでもOK
COPY requirements.txt ./
RUN if [ -s requirements.txt ]; then pip install --only-binary=:all: -r requirements.txt; fi

# ultralyticsは依存を引かせない（opencv-python等を避けたい場合）
RUN pip install ultralytics --no-deps

# torch/torchvision（CPU）を固定
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# アセットとコード
COPY models/yolo26n-seg.pt ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# ヘルス的な簡易チェック（任意）
RUN python -c "import ultralytics; print('ultralytics ok', ultralytics.__version__)"

# Lambdaランタイムとして起動（HTTP 8080）
CMD ["lambda_function.lambda_handler"]
