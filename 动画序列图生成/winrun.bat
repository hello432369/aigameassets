@echo off
chcp 65001 >nul
:: Sprite Forge - Windows 启动脚本
:: 双击运行即可启动自动处理器

cd /d "%~dp0"

echo ==============================================
echo 🚀 Sprite Forge 自动处理器
echo ==============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到 Python
    echo 请先安装 Python: https://python.org
    pause
    exit /b 1
)

:: 检查依赖
echo 📦 检查依赖...
pip install -q Pillow numpy watchdog 2>nul

:: 创建必要目录
if not exist input-0 mkdir input-0
if not exist input-1 mkdir input-1
if not exist output-0 mkdir output-0
if not exist output-1 mkdir output-1

echo.
echo ✅ 准备就绪！
echo.

:: 启动处理器
python scripts\auto_processor.py

echo.
pause
