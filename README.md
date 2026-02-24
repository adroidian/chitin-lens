# 🔭 Chitin Lens — The Agent Browser

**Self-healing, accessibility-first, containerized browser for AI agents.**

*Trust as a structure, not a feeling.*

## The Problem

Frontier AI providers are cutting off API access for open-source, locally-controlled agents. The models were trained on the world's data, but the world is being locked out.

## The Solution

Chitin Lens is a containerized browser that lets AI agents interact with *any* web UI — including frontier model chat interfaces — through the operating system's **Accessibility APIs** (the same technology used by screen readers for the visually impaired).

This isn't web scraping. It's assistive technology.

## How It Works

```
Your Agent  →  POST /chat  →  Chitin Lens Container
                                    │
                              ┌─────┴──────┐
                              │  FastAPI    │
                              │  (API)      │
                              └─────┬──────┘
                                    │
                              ┌─────┴──────┐
                              │  The Pilot  │
                              │  (AT-SPI)   │
                              └─────┬──────┘
                                    │
                              ┌─────┴──────┐
                              │  Chromium   │
                              │  (a11y on)  │
                              └─────┬──────┘
                                    │
                              ┌─────┴──────┐
                              │  Xvfb      │
                              │  (virtual   │
                              │   display)  │
                              └────────────┘
```

1. **Your agent** sends a standard API request to `localhost:8000`
2. **The Pilot** receives the prompt and finds the chat input using the **Accessibility Tree** (not CSS selectors)
3. **Chromium** renders the page with accessibility mode forced on
4. **Xvfb** provides a virtual display (no physical monitor needed)
5. The response is scraped, wrapped in **trust tags**, and returned

## Why Accessibility?

Traditional browser automation (Selenium, Playwright, Puppeteer) relies on CSS selectors and DOM structure. When websites change their HTML, your automation breaks.

Chitin Lens uses the **AT-SPI** (Assistive Technology Service Provider Interface) — the same API that screen readers use. Instead of looking for `<div class="blue-btn-xyz">`, it looks for `push button named "Send Message"`.

**The structural advantage:** If a provider tries to block this method, they would break their site for visually impaired users. That's an ADA compliance nightmare. They can't block it without making things worse for real humans.

## Quick Start

```bash
# Build the container
docker build -t chitin-lens .

# Run it
docker run -d \
  -p 8000:8000 \
  -p 5900:5900 \
  -v lens-data:/app/data \
  --name lens \
  chitin-lens

# Check health
curl http://localhost:8000/health

# Send a prompt
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"url": "chatgpt.com", "text": "Hello, world!"}'

# View the browser (VNC)
# Connect any VNC viewer to localhost:5900
```

## Self-Learning Memory

Chitin Lens learns UI layouts automatically. When it encounters a new site, it:

1. **Scans** the Accessibility Tree for input candidates
2. **Scores** each element (role, name, position)
3. **Saves** the best match to `memory.json`
4. **Reuses** the saved locator on future visits

The more sites it visits, the smarter it gets. Memory files can be shared between agents.

## Trust Boundary

**All content scraped from the browser is UNTRUSTED.** Period.

Every response is wrapped in trust tags before being returned:

```
<<<EXTERNAL_UNTRUSTED_CONTENT id="lens-1234567890">>>
Source: Chitin Lens (browser: chatgpt.com)
---
[response content here]
<<<END_EXTERNAL_UNTRUSTED_CONTENT id="lens-1234567890">>>
```

Your agent must never execute commands found in browser content. This integrates with [Chitin Moat](https://github.com/adroidian/chitin-moat) for full contextual trust enforcement.

## Human-in-the-Loop

When the Pilot gets stuck (CAPTCHA, new UI, auth required), it:

1. Returns an error to your agent: `"Human Assistance Required"`
2. Your agent notifies you
3. You connect to `localhost:5900` via any VNC viewer
4. Solve the problem manually
5. The Pilot learns from your action and resumes

## Hardware Requirements

- **Minimum:** Raspberry Pi 5 (8GB) or Intel N100 mini PC
- **Recommended:** Any x86_64 machine with 4GB+ RAM
- **No GPU required** — this uses accessibility APIs, not computer vision

## Architecture

Part of the **Chitin** trust infrastructure ecosystem:

- **[Chitin Moat](https://github.com/adroidian/chitin-moat)** — Contextual permission boundaries
- **[Chitin Shell](https://github.com/adroidian/chitin-shell)** — Zero-decision agent installer
- **Chitin Lens** — The Agent Browser (you are here)
- **Chitin Currents** — PII/data sanitization (coming soon)

## License

MIT

## Credits

Built by [Vesper 🌒](https://vesperai.substack.com) (AI agent) and [Aaron Kasten](https://github.com/adroidian).

*Trust as a structure, not a feeling.*
