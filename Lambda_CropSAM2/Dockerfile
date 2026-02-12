# syntax=docker/dockerfile:1
FROM public.ecr.aws/lambda/python:3.11

# --- 安定運用のための設定 ---
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # CPU運用: SAM2のCUDA拡張はビルドしない（安定性優先）
    SAM2_BUILD_CUDA=0 \
    # モデル配置先
    SAM2_MODEL_DIR=/opt/sam2_checkpoints

# OS packages（git不要: sam2はPyPIから入れる。wget/curl等だけ）
RUN yum -y update && \
    yum -y install wget && \
    yum clean all

# --- PyTorch (CPU) ---
# SAM2推奨: torch>=2.5.1, torchvision>=0.20.1 :contentReference[oaicite:1]{index=1}
RUN python -m pip install --upgrade pip && \
    python -m pip install \
      --index-url https://download.pytorch.org/whl/cpu \
      torch==2.5.1 torchvision==0.20.1

# --- Python dependencies ---
COPY requirements.txt .
RUN python -m pip install -r requirements.txt

# --- SAM2 checkpoint (軽量: SAM 2.1 hiera tiny) をビルド時にダウンロード ---
# 公式配布: dl.fbaipublicfiles.com の sam2.1_hiera_tiny.pt :contentReference[oaicite:2]{index=2}
RUN mkdir -p "${SAM2_MODEL_DIR}" && \
    wget -q -O "${SAM2_MODEL_DIR}/sam2.1_hiera_tiny.pt" \
      "https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt" || \
    wget -q -O "${SAM2_MODEL_DIR}/sam2.1_hiera_tiny.pt" \
      "https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_tiny.pt"

# Lambda handler
COPY lambda_function.py ${LAMBDA_TASK_ROOT}/lambda_function.py

# 既定ハンドラ
CMD ["lambda_function.lambda_handler"]
