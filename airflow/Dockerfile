FROM apache/airflow:2.9.3-python3.12

ENV PYTHONPATH="/app:$PYTHONPATH"

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

# ---------- 1. Install CPU-only PyTorch ----------
RUN pip install --no-cache-dir \
    torch==2.2.0+cpu torchvision==0.17.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# ---------- 2. Install Sentence-Transformers CPU ----------
RUN pip install --no-cache-dir "sentence-transformers[cpu]"

# ---------- 3. Install remaining dependencies ----------
RUN pip install --no-cache-dir \
    python-jobspy \
    pandas==2.2.0 \
    requests==2.32.3 \
    pymongo==4.8.0 \
    beautifulsoup4 \
    langdetect \
    pypdf \
    numpy
