#!/bin/bash
# GoldClaw DMG 构建脚本
# 产出: dist/GoldClaw.dmg — macOS 独立应用，双击即用

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VERSION="0.4.0"
APP_NAME="GoldClaw"
APP_DIR="dist/${APP_NAME}.app"
DMG_DIR="dist/dmg_temp"
DMG_OUTPUT="dist/${APP_NAME}-v${VERSION}.dmg"

echo "=== Building ${APP_NAME} v${VERSION} DMG ==="

# 清理
rm -rf "${APP_DIR}" "${DMG_DIR}" "${DMG_OUTPUT}"

echo "[1/4] PyInstaller building..."
.venv/bin/pyinstaller \
    --name "${APP_NAME}" \
    --windowed \
    --onedir \
    --noconfirm \
    --clean \
    --add-data "profiles:profiles" \
    --add-data "dashboard:dashboard" \
    --add-data ".env.example:.env.example" \
    --hidden-import=uvicorn.logging \
    --hidden-import=uvicorn.lifespan.on \
    --hidden-import=uvicorn.protocols.http.auto \
    --hidden-import=uvicorn.protocols.websockets.auto \
    --hidden-import=uvicorn.lifespan.off \
    --hidden-import=apscheduler.schedulers.background \
    --hidden-import=apscheduler.triggers.interval \
    --hidden-import=pydantic_settings \
    --hidden-import=httpx \
    --hidden-import=pywebview \
    --hidden-import=pywebview.platforms \
    --hidden-import=pywebview.platforms.cocoa \
    --hidden-import=webview \
    --distpath dist \
    --workpath build \
    app_main.py 2>&1 | tail -5

# 检查产物
if [ ! -d "dist/${APP_NAME}" ]; then
    echo "ERROR: PyInstaller failed - dist/${APP_NAME} not found"
    exit 1
fi

echo "[2/4] Creating .app bundle..."
mkdir -p "${APP_DIR}/Contents/MacOS"
mkdir -p "${APP_DIR}/Contents/Resources"

# 移动 PyInstaller 产物到 .app
cp -r "dist/${APP_NAME}/"* "${APP_DIR}/Contents/Resources/"

# 创建 launcher 脚本
cat > "${APP_DIR}/Contents/MacOS/GoldClaw" << 'LAUNCHER'
#!/bin/bash
RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
cd "$RESOURCES/_internal"
exec "$RESOURCES/GoldClaw"
LAUNCHER
chmod +x "${APP_DIR}/Contents/MacOS/GoldClaw"

# 创建 data 目录（在 _internal 下）
mkdir -p "${APP_DIR}/Contents/Resources/_internal/data"

# 复制 .env 到 _internal
if [ -f ".env" ]; then
    cp .env "${APP_DIR}/Contents/Resources/_internal/.env"
else
    cp .env.example "${APP_DIR}/Contents/Resources/_internal/.env"
fi

# 复制应用图标
cp dashboard/static/app_icon.icns "${APP_DIR}/Contents/Resources/app_icon.icns"

# Info.plist
cat > "${APP_DIR}/Contents/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>GoldClaw</string>
    <key>CFBundleDisplayName</key>
    <string>GoldClaw</string>
    <key>CFBundleIdentifier</key>
    <string>com.goldclaw.app</string>
    <key>CFBundleVersion</key>
    <string>${VERSION}</string>
    <key>CFBundleShortVersionString</key>
    <string>${VERSION}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleExecutable</key>
    <string>GoldClaw</string>
    <key>CFBundleIconFile</key>
    <string>app_icon</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
PLIST

echo "[3/4] Creating DMG..."
mkdir -p "${DMG_DIR}"
cp -r "${APP_DIR}" "${DMG_DIR}/"

# 创建「应用程序」快捷方式
ln -s /Applications "${DMG_DIR}/Applications"

# 创建 README
cat > "${DMG_DIR}/使用说明.txt" << README
GoldClaw v${VERSION} — 黄金量化交易模拟引擎 + Dashboard

1. 将 GoldClaw.app 拖到「应用程序」文件夹
2. 双击打开 GoldClaw.app
3. 首次打开可能需要在「系统设置 > 隐私与安全性」中允许
4. Dashboard 窗口会自动打开
5. 配置文件在 ~/GoldClaw/.env

数据目录: ~/GoldClaw/data/
README

# 用 hdiutil 创建 DMG（两步法保留符号链接）
hdiutil create \
    -volname "GoldClaw" \
    -srcfolder "${DMG_DIR}" \
    -ov \
    -format UDRW \
    -o "${DMG_OUTPUT}.rw.dmg"

hdiutil convert "${DMG_OUTPUT}.rw.dmg" \
    -format UDZO \
    -o "${DMG_OUTPUT}"

rm -f "${DMG_OUTPUT}.rw.dmg"

echo "[4/4] Cleanup..."
rm -rf "${DMG_DIR}"

DMG_SIZE=$(du -sh "${DMG_OUTPUT}" | cut -f1)
echo ""
echo "=== Build Complete ==="
echo "  Output: ${DMG_OUTPUT} (${DMG_SIZE})"
echo "  Double-click to install, drag GoldClaw.app to Applications"
