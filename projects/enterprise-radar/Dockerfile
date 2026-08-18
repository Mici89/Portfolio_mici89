# 企信雷达 - 生产部署镜像
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 系统字体（可选）：若将来让 PDF 用 Noto/文泉驿而非内置宋体，去掉下行注释并改 services/pdf_report.py 的 _register_font
# RUN apt-get update && apt-get install -y --no-install-recommends fonts-noto-cjk \
#     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

# headless 运行，关闭开发态自动重载
CMD ["streamlit", "run", "app.py", \
     "--server.headless", "true", \
     "--server.address", "0.0.0.0", \
     "--server.port", "8501"]
