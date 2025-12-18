#!/bin/bash
echo "========================================================"
echo "              SlotInsight Startup Script"
echo "========================================================"
echo ""

echo "[1/2] Installing dependencies..."
pip3 install -r requirements.txt
if [ $? -ne 0 ]; then
    echo ""
    echo "[Error] Failed to install dependencies. Please ensure Python3 and pip3 are installed."
    exit 1
fi

echo ""
echo "[2/2] Starting Streamlit App..."
echo "The app will open in your default browser shortly."
echo "Press Ctrl+C to stop."
echo ""

streamlit run app.py
