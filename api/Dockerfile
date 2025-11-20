FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt update && apt install -y \
    gcc \
    g++ \
    libmupdf-dev \
    mupdf-tools \
    curl \
    && apt clean && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy application code
COPY app /app/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
