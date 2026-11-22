FROM python:3.13-slim

WORKDIR /app

# 依存ライブラリを先に入れておくと、コードだけ変えたときに再ビルドが速くなる
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
ENV PYTHONPATH=/app/src

# DATABASE_URL を指定しなければSQLiteを使う（docker compose ではPostgreSQLを指定する）
RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite:////app/data/ledger.db

EXPOSE 8000
# 起動のたびにマイグレーションを最新まで実行してから、APIサーバーを起動する
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn ledger.main:app --host 0.0.0.0 --port 8000"]
