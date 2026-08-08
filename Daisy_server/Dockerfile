# Dockerfile
# 应用镜像：基于 daisy_server:base
# 只包含业务代码，构建速度快

ARG BASE_IMAGE=daisy_server:base
FROM ${BASE_IMAGE}

WORKDIR /app

# 设置时区为 Asia/Shanghai
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Ensure UTF-8 encoding
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 复制业务代码
# 注意：构建此镜像时，model 目录应在 .dockerignore 中，避免重复传输
COPY . /app/Daisy_server

# 将 .env 复制到工作目录，以便 pydantic 读取 (如果存在)
# 使用 cp 而不是 mv，因为 app/core/config.py 依赖于原位置的 .env
RUN if [ -f /app/Daisy_server/.env ]; then cp /app/Daisy_server/.env /app/.env; fi

ENV PYTHONPATH=/app:/app/Daisy_server

# Copy scripts
COPY run_worker.sh /app/run_worker.sh
RUN chmod +x /app/run_worker.sh

EXPOSE 30021

# Default command remains uvicorn, but can be overridden to run worker
CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-30021}"]
