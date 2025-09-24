#!/bin/bash

# Git Stats Dashboard Startup Script
# This script sets up the virtual environment, installs dependencies, and starts the Streamlit dashboard

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}🚀 Git Stats Dashboard Startup Script${NC}"
echo "Working directory: $SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Creating virtual environment...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${GREEN}✅ Virtual environment already exists${NC}"
fi

# Activate virtual environment
echo -e "${YELLOW}🔧 Activating virtual environment...${NC}"
source venv/bin/activate

# Check if requirements are installed
echo -e "${YELLOW}📋 Checking dependencies...${NC}"
if ! python -c "import streamlit, plotly, pandas" 2>/dev/null; then
    echo -e "${YELLOW}📥 Installing dependencies...${NC}"
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Dependencies installed${NC}"
else
    echo -e "${GREEN}✅ Dependencies already installed${NC}"
fi

# Kill any existing Streamlit processes on port 8501
echo -e "${YELLOW}🧹 Cleaning up existing processes...${NC}"
pkill -f "streamlit.*8501" 2>/dev/null || true

# Start Streamlit app in background
echo -e "${YELLOW}🚀 Starting Streamlit dashboard...${NC}"
nohup python -m streamlit run git_stats/streamlit_app.py --server.headless true --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &
STREAMLIT_PID=$!

# Wait a moment for the app to start
sleep 3

# Check if the process is running
if ps -p $STREAMLIT_PID > /dev/null; then
    echo -e "${GREEN}✅ Streamlit dashboard started successfully!${NC}"
    echo -e "${BLUE}📊 Dashboard URL: http://localhost:8501${NC}"
    echo -e "${BLUE}📝 Log file: streamlit.log${NC}"
    echo -e "${BLUE}🆔 Process ID: $STREAMLIT_PID${NC}"
    echo ""
    echo -e "${YELLOW}📋 First 100 lines of logs:${NC}"
    echo "----------------------------------------"
    head -100 streamlit.log
    echo "----------------------------------------"
    echo ""
    echo -e "${GREEN}🎉 Dashboard is ready! Open http://localhost:8501 in your browser${NC}"
    echo -e "${YELLOW}💡 To stop the dashboard, run: kill $STREAMLIT_PID${NC}"
    echo -e "${YELLOW}📝 To view logs: tail -f streamlit.log${NC}"
else
    echo -e "${RED}❌ Failed to start Streamlit dashboard${NC}"
    echo -e "${YELLOW}📋 Error logs:${NC}"
    cat streamlit.log
    exit 1
fi
