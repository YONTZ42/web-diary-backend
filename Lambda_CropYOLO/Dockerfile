FROM public.ecr.aws/lambda/python:3.11

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all:

RUN yum -y update && \
    yum -y install libgomp && \
    yum clean all

# pip 更新
RUN pip install --upgrade pip

# 依存を先に固定してから入れる（ここが重要）
COPY requirements.txt .
RUN pip install -r requirements.txt

# PyTorch (CPU) は明示ピン（将来の破壊的変更回避）
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# （任意）ultralyticsの一部機能で必要になることがあるので明示
RUN pip install ipython

# モデルの事前ダウンロード（ビルド時に同梱）
RUN python -c "from ultralytics import YOLO; YOLO('yolo11n-seg.pt')"

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
