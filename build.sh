#!/bin/bash
# GoldClaw 一键打包脚本
# 生成可分发的独立目录，双击 run.sh 即可启动

set -e

VERSION=${1:-"0.2.0"}
DIST_NAME="GoldClaw-v${VERSION}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="${SCRIPT_DIR}/dist/${DIST_NAME}"

echo "=== GoldClaw Build v${VERSION} ==="

# 清理
rm -rf "${DIST_DIR}"
mkdir -p "${DIST_DIR}"

# 复制源码
echo "[1/5] Copying source..."
cp -r app config internal profiles dashboard dashboard_api.py openclaw_bridge.py main.py run.py "${DIST_DIR}/"
# 清理 __pycache__
find "${DIST_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 复制配置模板
if [ -f .env ]; then
    cp .env "${DIST_DIR}/.env.example"
    echo "  .env.example created"
fi

# 创建数据目录
mkdir -p "${DIST_DIR}/data"

# 创建启动脚本
cat > "${DIST_DIR}/run.sh" << 'LAUNCH'
#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "First run: installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt --quiet
fi
.venv/bin/python3 run.py "$@"
LAUNCH
chmod +x "${DIST_DIR}/run.sh"

# 创建仅 Dashboard 模式脚本
cat > "${DIST_DIR}/dashboard-only.sh" << 'LAUNCH'
#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d ".venv" ]; then
    echo "First run: installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt --quiet
fi
echo "Dashboard-only mode (no Engine, reads existing DB)"
.venv/bin/python3 run.py --no-engine "$@"
LAUNCH
chmod +x "${DIST_DIR}/dashboard-only.sh"

# 复制 requirements
cp requirements.txt "${DIST_DIR}/"

# 创建 README
cat > "${DIST_DIR}/README.txt" << README
GoldClaw v${VERSION} — 黄金量化交易模拟引擎 + Dashboard

=== 启动方式 ===

1. 完整模式（Engine + Dashboard）:
   ./run.sh
   浏览器打开 http://localhost:8089/dashboard/

2. 仅 Dashboard（不启动 Engine，从已有数据库读取）:
   ./dashboard-only.sh

3. 首次运行会自动创建 .venv 并安装依赖，需要联网。

=== 配置 ===
复制 .env.example 为 .env，按需修改配置。

=== 数据 ===
数据库文件: data/goldclaw.db
日志文件: data/goldclaw.log
README

# 打包压缩
echo "[2/5] Creating archive..."
cd "${SCRIPT_DIR}/dist"
tar -czf "${DIST_NAME}.tar.gz" "${DIST_NAME}"
ZIP_SIZE=$(du -sh "${DIST_NAME}.tar.gz" | cut -f1)

echo ""
echo "=== Build Complete ==="
echo "  Output: dist/${DIST_NAME}.tar.gz (${ZIP_SIZE})"
echo "  Run:    cd ${DIST_NAME} && ./run.sh"
echo ""
echo "=== GitHub Release ==="
echo "  gh release create v${VERSION} dist/${DIST_NAME}.tar.gz \\"
echo "    --title \"GoldClaw v${VERSION}\" \\"
echo "    --notes \"详见 CHANGELOG\""
