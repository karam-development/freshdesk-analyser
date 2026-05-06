#!/bin/bash
# ============================================================
# Freshdesk AI Analyzer - Web App
# Double-click this file or run: ./run.sh
# ============================================================

cd "$(dirname "$0")"

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements.txt
fi

echo ""
echo "=========================================="
echo "  Freshdesk AI Analyzer"
echo "  Starting web app..."
echo "=========================================="
echo ""
echo "  Open your browser to:"
echo "  http://localhost:5000"
echo ""
echo "  Press Ctrl+C to stop"
echo "=========================================="
echo ""

python3 app.py
