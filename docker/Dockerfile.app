FROM python:3.9-slim

WORKDIR /app

# 依存関係のインストール
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pythonの依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのコードをコピー
COPY . .

# 必要なディレクトリの作成
RUN mkdir -p /app/uploads /app/outputs /tmp/ai-kirinuki

# 環境変数の設定
ENV PYTHONPATH=/app
ENV FLASK_APP=run.py
ENV FLASK_ENV=production
ENV PORT=5000

# Gunicornでサービスを起動
CMD gunicorn --bind 0.0.0.0:$PORT --workers 3 --timeout 120 "run:app"