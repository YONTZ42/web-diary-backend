FROM public.ecr.aws/lambda/python:3.11

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ONLY_BINARY=:all:

RUN yum -y update && yum -y install libgomp && yum clean all

# 1) まず numpy を固定（ここが超重要：sdist回避）
RUN pip install --upgrade pip && \
    pip install numpy==1.26.4

# 2) torch/torchvision（CPU wheel）
RUN pip install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# 3) opencv headless を先に入れる（cv2はこれに寄せる）
RUN pip install opencv-python-headless==4.10.0.84

# 4) ultralytics は deps を引かせない（opencv-python を引かせないため）
RUN pip install ultralytics==8.0.0 --no-deps

# 5) ultralytics が必要とする周辺 deps を明示固定（ビルド安定用）
RUN pip install \
      PyYAML==6.0.2 \
      tqdm==4.66.5 \
      psutil==6.0.0 \
      scipy==1.14.1 \
      matplotlib==3.9.2 \
      requests==2.32.3 \
      Pillow==10.4.0 \
      boto3==1.34.162

# 6) 残り（アプリ依存）
COPY requirements.txt .
RUN pip install -r requirements.txt

# 7) (推奨) モデル重みをビルド時に取得して同梱（MODEL_NAME がデフォならこれでOK）
#    ※ネットワーク制限がある実行環境対策
RUN python -c "from ultralytics import YOLO; YOLO('yolo26n-seg.pt')"

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
