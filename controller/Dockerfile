FROM python:3.11.15-slim

WORKDIR /app

# 依赖层：仅 pyproject.toml 变化时才重新解析安装依赖（层缓存命中）
# 源码变更不会破坏此层，CI/本地重复构建均秒级命中
# 安装中文字体（图表中文渲染需要）
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN python3 -c "import tomllib; deps = tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']; print('\n'.join(deps))" > /tmp/deps.txt \
    && pip install --no-cache-dir -r /tmp/deps.txt

# 源码层：只重装包本身（--no-deps 跳过依赖）
# pip wheel 走 BuildKit 缓存卷，源码反复变更也不重复下载
COPY . ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .

# Default command (will be overridden by docker-compose for dev)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "42791"]
