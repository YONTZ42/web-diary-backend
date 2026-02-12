# ---- AWS Lambda Python base image ----
FROM public.ecr.aws/lambda/python:3.11

# (任意) pip高速化
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# OS deps (最低限)
# - libgomp: 一部の依存で必要になることがある
RUN yum -y update && \
    yum -y install \
      libgomp \
    && yum clean all

# ---- Python deps ----
# まずtorchをCPUで入れる（LambdaでGPUは基本使わない前提）
# PyTorch公式CPU wheel index
RUN pip install --upgrade pip && \
    pip install --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# requirements
COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- App ----
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

# Handler
CMD ["lambda_function.lambda_handler"]
