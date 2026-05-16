# ==================== 多阶段构建 ====================
# 构建阶段
FROM python:3.11-slim AS builder

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ==================== 运行阶段 ====================
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制依赖
COPY --from=builder /root/.local /root/.local

# 确保脚本在 PATH 中
ENV PATH=/root/.local/bin:$PATH

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查（使用 python 内置 urllib，无需额外安装 curl）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
