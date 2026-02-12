FROM public.ecr.aws/lambda/python:3.11

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all:

RUN yum -y update && yum -y install libgomp && yum clean all
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --only-binary=:all: -r requirements.txt

# ultralyticsは依存を引かせない（opencv-pythonを防ぐ）
RUN pip install ultralytics==8.2.0 --no-deps

# torch/torchvision（CPU）もここで固定（requirementsに入れない）
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# （任意）インポート検証
RUN python -c "import cv2; import ultralytics; print('cv2 ok', cv2.__version__); print('ultralytics ok', ultralytics.__version__)"

# モデル同梱（必要なら）
RUN python -c "from ultralytics import YOLO; YOLO('yolo26n-seg.pt')"

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
