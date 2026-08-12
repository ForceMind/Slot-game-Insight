@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo                  SlotInsight 启动器
echo ========================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo 未找到 Python 3，请先安装 Python 3 后重试。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] 正在创建本地运行环境...
    python -m venv .venv
    if %errorlevel% neq 0 goto :error
) else (
    echo [1/3] 本地运行环境已就绪。
)

.venv\Scripts\python.exe -c "import streamlit, pandas, plotly, openpyxl, st_aggrid" >nul 2>nul
if %errorlevel% neq 0 (
    echo [2/3] 正在安装所需组件，首次启动会稍久...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
    if %errorlevel% neq 0 goto :error
) else (
    echo [2/3] 所需组件已安装。
)

echo [3/3] 正在打开数据面板...
.venv\Scripts\python.exe -m streamlit run app.py --browser.gatherUsageStats=false --server.showEmailPrompt=false
exit /b 0

:error
echo.
echo 启动失败，请保留本窗口中的错误信息。
pause
exit /b 1
