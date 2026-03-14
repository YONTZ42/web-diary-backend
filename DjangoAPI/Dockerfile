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
    mkdir -p /app/.u2net

# --- ここでモデルを事前にダウンロード ---
# python -c を使ってインラインで実行します
RUN python -c "from rembg import new_session; \
models = ['isnet-general-use', 'isnet-anime', 'birefnet-general-lite']; \
[new_session(m) for m in models]"
# --------------------------------------
    
# アプリ本体は後からコピー
COPY . /app/

RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

EXPOSE 8080

CMD ["/app/start.sh"]