# 手順1で作ったベースイメージを参照する
FROM 563224521754.dkr.ecr.ap-northeast-1.amazonaws.com/web-diary/crop-yolo-lambda/packages:latest

COPY models/yolo26n-seg.pt ${LAMBDA_TASK_ROOT}/yolo26n-seg.pt
ENV MODEL_NAME=yolo26n-seg.pt \
    YOLO_CONFIG_DIR=/temp/Ultralytics

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
