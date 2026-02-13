# 手順1で作ったベースイメージを参照する
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

COPY models/yolo26n-seg.pt ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
ENV MODEL_NAME=yolo26n-seg.pt \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
