#!/bin/bash

# Stop API Server Script

echo "⏹️  Stopping API Server..."

PID=$(ps aux | grep '[a]pi_server.py' | awk '{print $2}')
PORT_PID=$(lsof -ti tcp:8000)

if [ -n "$PID" ]; then
    echo "Found server (PID: $PID)"
    kill $PID
    sleep 1
    
    # Check if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  Force killing..."
        kill -9 $PID
    fi
    
    echo "✅ Server stopped"
else
    echo "ℹ️  Server is not running"
fi

if [ -n "$PORT_PID" ]; then
    echo "Found process on port 8000 (PID: $PORT_PID)"
    kill $PORT_PID 2>/dev/null || true
    sleep 1
    if ps -p $PORT_PID > /dev/null 2>&1; then
        echo "⚠️  Force killing port 8000 process..."
        kill -9 $PORT_PID 2>/dev/null || true
    fi
    echo "✅ Port 8000 released"
fi
