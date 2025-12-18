@echo off
chcp 65001 >nul
echo ========================================================
echo               SlotInsight 启动脚本
echo ========================================================
echo.

echo [1/2] 正在检查并安装依赖库...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [错误] 依赖安装失败。请确保您已安装 Python 并且 pip 已添加到环境变量。
    pause
    exit /b
)

echo.
echo [2/2] 正在启动 Streamlit 应用...
echo 应用启动后会自动打开默认浏览器。
echo 如需关闭应用，请直接关闭此窗口。
echo.

streamlit run app.py

pause
