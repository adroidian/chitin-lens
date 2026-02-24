#!/bin/bash
# Chitin Lens — Startup Script
# Orchestrates: Display → D-Bus → Window Manager → Browser → Agent API

set -e

echo "🔭 Chitin Lens starting..."

# 0. Create Xauthority file (needed by pyautogui/Xlib)
touch /root/.Xauthority

# 1. Start D-Bus (required for AT-SPI accessibility)
echo "  [1/6] Starting D-Bus..."
# Start the system bus (needed by AT-SPI registry)
mkdir -p /run/dbus
dbus-daemon --system --fork 2>/dev/null || true
# Start the session bus
eval $(dbus-launch --sh-syntax)
export DBUS_SESSION_BUS_ADDRESS

# 2. Start Xvfb (Virtual Framebuffer — fake monitor)
echo "  [2/6] Starting virtual display..."
Xvfb :99 -screen 0 1920x1080x24 -ac &
XVFB_PID=$!
export DISPLAY=:99
sleep 2

# 3. Start Fluxbox (Window Manager — handles focus)
echo "  [3/6] Starting window manager..."
fluxbox &
sleep 1

# 4. Start VNC Server (Human-in-the-loop rescue mode)
echo "  [4/6] Starting VNC server on :5900..."
x11vnc -display :99 -forever -nopw -quiet -shared &
sleep 1

# 5. Configure Accessibility Environment
echo "  [5/6] Enabling accessibility layer..."
export GTK_MODULES=gail:atk-bridge
export QT_ACCESSIBILITY=1
export NO_AT_BRIDGE=0
export ACCESSIBILITY_ENABLED=1

# 6. Launch Chromium in Accessibility Mode
echo "  [6/6] Launching browser..."
chromium --no-sandbox \
         --disable-gpu \
         --disable-dev-shm-usage \
         --force-renderer-accessibility \
         --start-maximized \
         --remote-debugging-port=9222 \
         --remote-allow-origins=* \
         --user-data-dir=/app/data/chrome-profile \
         "about:blank" &
CHROME_PID=$!

# Wait for browser to initialize
echo "  Waiting for browser to stabilize..."
sleep 5

# Verify browser is running
if kill -0 $CHROME_PID 2>/dev/null; then
    echo "  ✅ Browser running (PID: $CHROME_PID)"
else
    echo "  ❌ Browser failed to start"
    exit 1
fi

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║  🔭 Chitin Lens is ready                  ║"
echo "║                                           ║"
echo "║  API:  http://localhost:8000              ║"
echo "║  VNC:  vnc://localhost:5900               ║"
echo "║  CDP:  http://localhost:9222              ║"
echo "║                                           ║"
echo "║  Trust as a structure, not a feeling. 🌒  ║"
echo "╚═══════════════════════════════════════════╝"
echo ""

# Start the Agent API (blocking — keeps container alive)
exec python3 -m uvicorn pilot:app --host 0.0.0.0 --port 8000 --log-level info
