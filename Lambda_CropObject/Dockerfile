FROM public.ecr.aws/lambda/python:3.10

COPY requirements.txt .
RUN python -m pip install -U pip setuptools wheel

# まず numpy を固定して入れる（wheelで入る）
RUN python -m pip install "numpy==1.26.4"

# 次に requirements（依存解決でnumpyを上げないように）
RUN python -m pip install -r requirements.txt --no-cache-dir --no-deps
RUN python -m pip install rembg==2.0.69 --no-cache-dir

COPY lambda_function.py ${LAMBDA_TASK_ROOT}/
CMD ["lambda_function.lambda_handler"]
