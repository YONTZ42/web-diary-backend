FROM public.ecr.aws/lambda/python:3.11

# 環境変数の設定
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# OSの依存ライブラリ (libgompはOpenMPの並列処理に必須)
RUN yum -y update && \
    yum -y install libgomp && \
    yum clean all

# 1) pipを最新にする
RUN pip install --upgrade pip

# 2) OpenCV Headless を最初に入れる
# これを先に入れることで、ultralyticsが依存で重いGUI版を入れるのを防ぎます
RUN pip install numpy==1.26.4
RUN pip install opencv-python-headless==4.10.0.84 --no-deps

# 3) PyTorch (CPU版)
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 4) その他の依存関係を一括インストール
# --no-deps は使わず、正常に構成させます
COPY requirements.txt .
RUN pip install -r requirements.txt

# 5) IPython を明示的に追加 (ultralyticsの一部機能で必須)
RUN pip install ipython

# 6) モデルの事前ダウンロード (ビルド時に同梱)
# 最新の YOLO11 または YOLO26 を指定
RUN python -c "from ultralytics import YOLO; YOLO('yolo11n-seg.pt')"

# 7) アプリケーションコード
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/

CMD ["lambda_function.lambda_handler"]