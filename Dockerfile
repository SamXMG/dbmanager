# dbmanager 容器镜像: 多阶段构建(路线图 P1-6 Docker 瘦身)
# 构建: docker build -t dbmanager .
# 运行: docker run -p 8770:8770 -v dbmanager_data:/app/data dbmanager
# 访问: http://<host>:8770/v2 (Vue3 前端)
# 瘦身要点: 编译工具链(gcc/g++/unixodbc-dev)只在 pybuilder 阶段; runtime 仅保留运行依赖

# ---- 阶段1: 前端构建(frontend/dist) ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 阶段2: Python 依赖预编译(builder) ----
# 编译型驱动(psycopg2/oracledb 等)需要 gcc/g++/unixodbc-dev —— 仅在此阶段
FROM python:3.12-slim AS pybuilder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip wheel --no-cache-dir -r requirements.txt -w /build/wheels

# ---- 阶段3: Python 运行时(无编译工具链) ----
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DBM_NO_OPEN=1

# 运行时只需 unixodbc(无 -dev) + curl(ODBC 安装脚本) + gnupg
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unixodbc \
    && rm -rf /var/lib/apt/lists/*

# 微软 ODBC Driver 18 for SQL Server(可选; 不连 SQL Server 可去掉, 启动不受影响)
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# 从 builder 拷预编译 wheel, 离线安装(无需 gcc/g++)
COPY --from=pybuilder /build/wheels ./wheels
RUN pip install --no-cache-dir --no-index ./wheels && rm -rf ./wheels

# 后端全部源码(含重构后的 services/routes 分层)
COPY app.py config.py crypto.py dbcore.py handler.py ops.py store.py tunnel.py auth.py \
     logging_conf.py task_sched.py get_ipv6.py sqlitedb.py metrics.py \
     scanner.py handler_security.py ./
COPY services ./services
COPY routes ./routes

# 前端构建产物(阶段1); 旧 js/ css/ index.html 已随双前端退役删除(路线图 1.2)
COPY --from=fe /fe/dist ./frontend/dist

# 运行时数据目录(连接配置/密钥/日志)
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 8770

CMD ["python", "app.py"]
