# 月印 Moonprint · 生产镜像
# 贴图不打进镜像：首次运行自动从 NASA 下载到 /data/textures（挂载卷持久化）
FROM python:3.11-slim

# 中文渲染可能需要的系统字体 + curl（健康检查用）
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 先装依赖（利用 Docker 层缓存，代码改动不用重装依赖）
COPY pyproject.toml README.md ./
COPY moonbirthday ./moonbirthday
RUN pip install --no-cache-dir .

# 贴图缓存目录（挂载卷，跨容器重启不丢）
ENV MOONPRINT_TEXDIR=/data/textures
VOLUME ["/data"]

EXPOSE 8765

# 绑定 0.0.0.0 才能被外部访问；--no-browser 避免在容器里尝试开浏览器
CMD ["python3", "-m", "moonbirthday", "serve", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]
