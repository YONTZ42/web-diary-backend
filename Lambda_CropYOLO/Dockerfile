# 手順1で作ったベースイメージを参照する
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

RUN curl -L "$MODEL_URL" -o ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
RUN curl -L "$MODEL_URL" -o ${LAMBDA_TASK_ROOT}/yolo26s-seg.pt

ENV MODEL_NAME=yolo26n-seg.pt \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
