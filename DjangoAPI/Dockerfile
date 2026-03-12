FROM python:3.9

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    U2NET_HOME=/app/.u2net \
    MODEL_NAME=isnet-general-use \
    OMP_NUM_THREADS=1 \
    OMP_WAIT_POLICY=PASSIVE

# 依存関係だけ先にコピーして、コード変更時の再buildを速くする
COPY requirements.txt /app/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefer-binary -r /app/requirements.txt && \
    mkdir -p /app/.u2net && \
    python - <<'PY'
import os
import urllib.request


model_repository_name = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/"
model_names = [
    "isnet-general-use.onnx"
    #"isnet-anime.onnx",
    #"birefnet-general-lite.onnx"
]
for model_name in model_names:
    url = model_repository_name + model_name
    dest_dir = "/app/.u2net"
    dest_path = f"{dest_dir}/{model_name}"

    os.makedirs(dest_dir, exist_ok=True)

    if not os.path.exists(dest_path):
        print(f"downloading model to {dest_path}")
        urllib.request.urlretrieve(url, dest_path)
    else:
        print(f"model already exists: {dest_path}")
PY


# アプリ本体は後からコピー
COPY . /app/

RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]