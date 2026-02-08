# Pythonのイメージを指定
FROM python:3.9

# コンテナ内の作業ディレクトリを設定
WORKDIR /app

# 環境変数の設定 (Pythonがログをすぐ出力するように)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 依存関係をコピーしてインストール
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# ローカルのプロジェクトファイルをすべてコピー
COPY . /app/