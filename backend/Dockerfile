FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# 先装依赖再拷代码：改代码不会让依赖层缓存失效，重新部署快很多。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# SQLite 库文件和上传的包裹照片都放在挂载出去的卷上，
# 不然每次重新部署，订单数据和仓库拍的留底照片会一起没。
ENV DATABASE_URL=sqlite:////data/suda.db \
    UPLOAD_DIR=/data/uploads
VOLUME ["/data"]

EXPOSE 8811

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8811/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8811"]
