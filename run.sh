#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

echo "========================================================"
echo "                 SlotInsight 启动器"
echo "========================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 Python 3，请先安装 Python 3 后重试。"
    exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
    echo "[1/3] 正在创建本地运行环境…"
    python3 -m venv .venv || exit 1
else
    echo "[1/3] 本地运行环境已就绪。"
fi

PYTHON="$SCRIPT_DIR/.venv/bin/python"

if ! "$PYTHON" -c "import streamlit, pandas, plotly, openpyxl, st_aggrid" >/dev/null 2>&1; then
    echo "[2/3] 正在安装所需组件，首次启动会稍久…"
    "$PYTHON" -m pip install -r requirements.txt || exit 1
else
    echo "[2/3] 所需组件已安装。"
fi

echo "[3/3] 正在打开数据面板…"
echo "关闭本窗口即可停止面板。"
echo

exec "$PYTHON" -m streamlit run app.py \
    --browser.gatherUsageStats=false \
    --server.headless=false \
    --server.showEmailPrompt=false
