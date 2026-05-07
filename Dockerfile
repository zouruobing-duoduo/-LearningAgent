FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# HF Spaces 要求暴露 7860 端口
EXPOSE 7860

CMD ["python", "main.py"]
