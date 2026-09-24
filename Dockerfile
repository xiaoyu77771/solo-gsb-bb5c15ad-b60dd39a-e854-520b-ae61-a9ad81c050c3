FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAN_DB_PATH=/data/plans.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 结果保存目录（由 Compose 挂载命名卷）
RUN mkdir -p /data

EXPOSE 8000

# 依赖安装与数据库初始化均在容器启动时完成（建表见 storage lifespan）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
