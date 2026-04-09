# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('profiles', 'profiles'), ('dashboard', 'dashboard'), ('.env.example', '.env.example')],
    hiddenimports=['uvicorn.logging', 'uvicorn.lifespan.on', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.off', 'apscheduler.schedulers.background', 'apscheduler.triggers.interval', 'pydantic_settings', 'httpx', 'pywebview', 'pywebview.platforms', 'pywebview.platforms.cocoa', 'webview'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GoldClaw',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GoldClaw',
)
app = BUNDLE(
    coll,
    name='GoldClaw.app',
    icon=None,
    bundle_identifier=None,
)
