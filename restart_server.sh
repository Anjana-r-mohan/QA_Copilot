#!/bin/bash

# Restart API Server Script
# Kills old server and starts fresh with latest code

echo "🔄 Restarting API Server..."

# Find and kill existing server
PID=$(ps aux | grep '[a]pi_server.py' | awk '{print $2}')
PORT_PID=$(lsof -ti tcp:8000)

if [ -n "$PID" ]; then
    echo "⏹️  Stopping old server (PID: $PID)..."
    kill $PID
    sleep 2
    
    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  Force killing..."
        kill -9 $PID
    fi
    
    echo "✅ Old server stopped"
else
    echo "ℹ️  No running server found"
fi

if [ -n "$PORT_PID" ]; then
    echo "⏹️  Releasing port 8000 (PID: $PORT_PID)..."
    kill $PORT_PID 2>/dev/null || true
    sleep 1
    if ps -p $PORT_PID > /dev/null 2>&1; then
        echo "⚠️  Force killing port process..."
        kill -9 $PORT_PID 2>/dev/null || true
    fi
fi

# Start new server
echo "🚀 Starting API server..."
cd /Users/anjana.mohan/QaCoPilot

# Check if venv exists and activate it
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

PYTHON_BIN=""
if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "❌ Python interpreter not found (python/python3)"
    exit 1
fi

# Start server in background
nohup "$PYTHON_BIN" api_server.py > server.log 2>&1 &

NEW_PID=$!
echo "✅ Server started (PID: $NEW_PID)"
echo "📋 Logs: tail -f server.log"
echo ""
echo "Server is running at http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
