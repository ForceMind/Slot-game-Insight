#!/bin/bash
echo "========================================================"
echo "              SlotInsight Startup Script"
echo "========================================================"
echo ""

# 0. 配置 Streamlit 禁用欢迎界面 (Bypass Email Prompt)
# 创建 .streamlit 目录（如果不存在）
mkdir -p ~/.streamlit/

# 创建或追加配置到 credentials.toml 以跳过 email 提示
if [ ! -f ~/.streamlit/credentials.toml ]; then
    echo "[general]" > ~/.streamlit/credentials.toml
    echo "email = \"\"" >> ~/.streamlit/credentials.toml
    echo "Configured Streamlit to skip email prompt."
fi

# 确保 config.toml 存在且 headless = true (可选，防止浏览器弹窗失败报错)
# mkdir -p .streamlit
# echo "[server]\nheadless = true" > .streamlit/config.toml

echo "[1/2] Installing dependencies..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "[Error] Failed to install dependencies. Please ensure Python3 and pip3 are installed."
    echo "Try running: brew install python3 (if you have Homebrew)"
    exit 1
fi

echo ""
echo "[2/2] Starting Streamlit App..."
echo "The app will open in your default browser shortly."
echo "Press Ctrl+C to stop."
echo ""

# 使用 --server.headless=false 确保它尝试打开浏览器
# 使用 --browser.gatherUsageStats=false 禁用数据收集
streamlit run app.py --browser.gatherUsageStats=false
