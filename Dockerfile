# Pythonのイメージを指定
FROM python:3.9

# コンテナ内の作業ディレクトリを設定
WORKDIR /app

# 環境変数の設定 (Pythonがログをすぐ出力するように)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

# 依存関係をコピーしてインストール
COPY requirements.txt /app/
# 静的ファイルを配置するディレクトリを先に作っておく（権限エラー回避）
# 静的ファイルを集める（--noinputで対話をスキップ）
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# ローカルのプロジェクトファイルをすべてコピー
COPY . /app/

RUN mkdir -p /app/staticfiles


# ★ App Runnerが通信に使用する8080ポートを開放
EXPOSE 8080

# ★ Gunicornを使用してDjangoを起動（ポート8080にバインド）
# --bind 0.0.0.0:8080 により、コンテナ外部からの接続を許可します

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh
CMD ["/app/start.sh"]
