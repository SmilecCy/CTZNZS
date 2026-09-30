
# ============================================================

# 后端 Docker 打包说明书

# 用途：把 Python 后端打包成一个"集装箱"

# ============================================================

# 1. 选基础箱子（已经装好 Python 3.11 的 Linux）
FROM python:3.11-slim

# 2. 设定工作目录
WORKDIR /app

# 3. 先装系统依赖（PyMuPDF、paddlepaddle 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 4. 复制依赖清单，安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 复制所有项目文件
COPY . .

# 6. 暴露端口
EXPOSE 5174

# 7. 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5174"]
