FROM python:3.13-slim

WORKDIR /app

# 依存ライブラリを先に入れておくと、コードだけ変えたときに再ビルドが速くなる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
ENV PYTHONPATH=/app/src

# データベースはこのフォルダに置き、docker compose でボリュームをつなぐ
RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite:////app/data/ledger.db

EXPOSE 8000
CMD ["uvicorn", "ledger.main:app", "--host", "0.0.0.0", "--port", "8000"]
