#!/bin/bash
cd "$(dirname "$0")"

# Install Python dependencies if needed
pip3 install flask anthropic requests python-dotenv pdfplumber python-docx openpyxl reportlab python-pptx google-api-python-client google-auth google-auth-httplib2 2>/dev/null

# Install Node.js dependencies if needed (for Word doc generation)
if [ ! -d "node_modules/docx" ]; then
  echo "Installing Node.js dependencies..."
  npm install 2>/dev/null
fi

echo ""
echo "=========================================="
echo "  Freshdesk AI Analyzer"
echo "  Open http://localhost:5000 in Chrome"
echo "=========================================="
echo ""

python3 app.py
