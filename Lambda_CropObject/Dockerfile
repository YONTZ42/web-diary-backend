FROM public.ecr.aws/lambda/python:3.11


# numpy がソースビルドになるのでビルドツールを入れる（確実に通すため）
RUN yum -y install gcc gcc-c++ make && yum clean all

# 依存（rembgはonnxruntime等を引く）
COPY requirements.txt .
RUN python -m pip install -U pip setuptools wheel
RUN python -m pip install -r requirements.txt --no-cache-dir

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]
