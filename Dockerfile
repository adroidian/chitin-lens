# Chitin Lens — The Agent Browser
# Self-healing, accessibility-first, containerized browser for AI agents
# Trust as a structure, not a feeling.

FROM python:3.10-slim

# Install system dependencies
# xvfb: Virtual framebuffer (fake monitor in RAM)
# fluxbox: Minimal window manager (focus management for accessibility)
# x11vnc: VNC server for human-in-the-loop debugging
# chromium: The browser engine
# at-spi2-core: Linux Accessibility Bus (the "screen reader" interface)
# gir1.2-atspi-2.0: AT-SPI typelib (required for pyatspi via GObject introspection)
# libgirepository1.0-dev: GObject introspection dev headers (for PyGObject pip install)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    fluxbox \
    x11vnc \
    chromium \
    chromium-driver \
    at-spi2-core \
    dbus-x11 \
    gir1.2-gtk-3.0 \
    gir1.2-atspi-2.0 \
    gcc \
    pkg-config \
    libcairo2-dev \
    libgirepository1.0-dev \
    xdotool \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pyautogui --no-deps && \
    pip install --no-cache-dir pytweening mouseinfo pygetwindow pyperclip pyrect pyscreeze 2>/dev/null || true

# Copy application code
COPY pilot.py .
COPY start.sh .
COPY memory.json .

# Make startup script executable
RUN chmod +x start.sh

# Create volume mount point for persistent memory
VOLUME /app/data

# Expose ports
# 8000: FastAPI (agent communication)
# 5900: VNC (human-in-the-loop debugging)
# 9222: Chrome DevTools Protocol (optional direct CDP access)
EXPOSE 8000 5900 9222

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run
CMD ["./start.sh"]
