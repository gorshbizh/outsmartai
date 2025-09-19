#!/bin/bash

# Start development servers for OutSmartAI Whiteboard
# This script starts both the TypeScript frontend server and Python backend server

echo "Starting OutSmartAI Whiteboard Development Environment..."

# Check if Node.js dependencies are installed
if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

# Check if Python dependencies are installed
if [ ! -f "backend/.venv/bin/activate" ]; then
    echo "Setting up Python virtual environment..."
    cd backend
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# Build TypeScript
echo "Building TypeScript..."
npm run build

# Start backend server in background
echo "Starting Python backend server..."
cd backend
source .venv/bin/activate
python app.py &
BACKEND_PID=$!
cd ..

# Wait a moment for backend to start
sleep 2

# Start frontend server
echo "Starting TypeScript frontend server..."
npm start &
FRONTEND_PID=$!

echo "Servers started:"
echo "- Frontend (TypeScript): http://localhost:3000"
echo "- Backend (Python): http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop both servers"

# Function to cleanup on exit
cleanup() {
    echo "Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    exit 0
}

# Trap Ctrl+C
trap cleanup INT

# Wait for both processes
wait