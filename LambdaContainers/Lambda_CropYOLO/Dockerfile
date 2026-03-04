ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ENV MODEL_NAME=yolo26n-seg.pt \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

# workflow で事前に落としている想定
COPY models/yolo26n-seg.pt ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
COPY models/yolo26s-seg.pt ${LAMBDA_TASK_ROOT}/yolo26s-seg.pt

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
