#!/bin/bash
# Sprite Forge - macOS 启动脚本
# 双击运行即可启动自动处理器

cd "$(dirname "$0")"

echo "=============================================="
echo "🚀 Sprite Forge 自动处理器"
echo "=============================================="
echo ""

# 检查 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 Python3"
    echo "请先安装 Python: https://python.org"
    read -p "按回车键退出..."
    exit 1
fi

# 检查依赖
echo "📦 检查依赖..."
pip3 install -q Pillow numpy watchdog 2>/dev/null

# 创建必要目录
mkdir -p input-0 input-1 output-0 output-1

echo ""
echo "✅ 准备就绪！"
echo ""

# 启动处理器
python3 scripts/auto_processor.py

echo ""
read -p "按回车键关闭窗口..."
