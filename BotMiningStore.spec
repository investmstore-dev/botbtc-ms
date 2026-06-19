# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — BOT Mining Store (bot + dashboard + setup en un .exe)
# Build:  pyinstaller --clean -y BotMiningStore.spec
# Salida: dist/BotMiningStore.exe (un solo archivo)

a = Analysis(
    ['app.py'],
    pathex=['.'],
    binaries=[],
    # Recursos de solo lectura embebidos (setup.html + dashboard en web/dashboard)
    datas=[('web', 'web')],
    hiddenimports=[
        'MetaTrader5',
        'pandas', 'numpy', 'requests',
        # imports dinamicos (account_manager los carga por nombre)
        'utils.brokers.bybit_broker',
        'utils.brokers.mt5_broker',
        'logic.bot', 'logic.strategy',
        'utils.control_server', 'utils.data_server', 'utils.dashboard_server',
        'utils.account_manager', 'utils.bybit_connector', 'utils.state_manager',
        'utils.notifier', 'config.settings',
    ],
    excludes=['matplotlib', 'tkinter'],
)

pyz = PYZ(a.pure)

# onefile: se incluyen binaries/datas en EXE y NO se usa COLLECT
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BotMiningStore',
    debug=False,
    strip=False,
    upx=True,
    console=True,          # muestra estado/logs; poner False para sin ventana
)
