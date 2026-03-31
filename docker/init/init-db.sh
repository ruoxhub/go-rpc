#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# 使用 pg_isready 等待数据库就绪
while ! pg_isready -h "${POSTGRES_HOST:-postgres}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}"; do
    sleep 1
done

echo "PostgreSQL is ready!"

# 如果需要，可以在此处执行额外的初始化逻辑
echo "Database initialization complete."
