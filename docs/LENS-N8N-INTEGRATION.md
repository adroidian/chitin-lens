# Chitin Lens + n8n Integration Blueprint

## The Thesis
Chitin Lens gives agents browser hands. n8n gives agents workflow logic. Together, they create **autonomous multi-service pipelines that use the same web UIs humans use** — no API keys, no OAuth apps, no rate limits.

## What We've Proven Works (Today)

| Service | Via Lens | Action | Selectors Known |
|---------|---------|--------|-----------------|
| **Proton Mail** | ✅ | Read inbox, compose, send | Full selector map in memory.json |
| **Google Gemini** | ✅ | Send prompts, read responses | `.response-content` div |
| **ChatGPT** | ✅ | Send prompts, read responses | `#prompt-textarea`, `button[aria-label="Send prompt"]` |
| **Claude** | ✅ | Send prompts, read responses | `[data-testid="chat-input"]`, `[data-is-streaming]` |
| **Google AI Studio** | ✅ | Text prompts, image gen (Nano Banana), TTS, code gen | Textarea + Run button |
| **NotebookLM** | ✅ | Create notebooks, add sources, generate audio/video overviews | PRO access, full selector map |
| **Twitter/X** | ✅ | Post tweets, read timeline | Via Forge CDP |
| **dev.to** | ✅ | Publish articles | Via Forge CDP |
| **Substack** | ✅ | Manage newsletter | Via Forge CDP |
| **Google Stitch** | ⚠️ | Text-to-UI design (blocked by Angular framework) | Needs AT-SPI fallback |

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    n8n on Omni                        │
│               (http://192.168.0.161:5678)             │
│                                                       │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Trigger │→│ HTTP Req  │→│ Process   │→ Output    │
│  │ (cron/  │  │ to Lens   │  │ Response  │            │
│  │  webhook)│  │ API       │  │           │            │
│  └─────────┘  └──────────┘  └──────────┘            │
│                     │                                 │
└─────────────────────┼─────────────────────────────────┘
                      │ POST /chat, /email, /navigate
                      ▼
┌──────────────────────────────────────────────────────┐
│              Chitin Lens Container                     │
│            (omni:8100, CDP:9222 internal)              │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ FastAPI  │→│ Pilot    │→│ Chromium  │           │
│  │ (router) │  │ (AT-SPI) │  │ (a11y on) │           │
│  └──────────┘  └──────────┘  └──────────┘           │
│                                                       │
│  Sessions: Gemini | ChatGPT | Claude | Proton | X    │
└──────────────────────────────────────────────────────┘
```

## Workflow Recipes

### 1. Multi-Model Consensus Engine
**Trigger:** Webhook from OpenClaw or cron schedule
**Flow:**
1. n8n receives a question/task
2. HTTP Request → Lens `/chat?model=gemini` (send prompt)
3. HTTP Request → Lens `/chat?model=chatgpt` (same prompt)
4. HTTP Request → Lens `/chat?model=claude` (same prompt)
5. n8n Code node: Compare responses, extract consensus
6. Output: Telegram notification / email / database

**Use case:** Due diligence, fact-checking, strategy brainstorming
**Revenue:** "Supermind Consensus" recipe in $49 Pro bundle

### 2. Email-to-AI Pipeline
**Trigger:** n8n cron (every 15 min)
**Flow:**
1. HTTP Request → Lens `/email/inbox` (read unread emails from Proton)
2. n8n Code: Filter important emails, extract content
3. HTTP Request → Lens `/chat?model=claude` (summarize/draft reply)
4. n8n IF: If reply needed → Lens `/email/send` (send via Proton)
5. n8n Telegram: Notify human of actions taken

**Use case:** Email triage, auto-reply drafting
**Revenue:** "AI Email Assistant" recipe

### 3. Content Pipeline (Blog → Social → Newsletter)
**Trigger:** Manual or scheduled
**Flow:**
1. n8n receives draft content (from Notion, file, or AI-generated)
2. HTTP Request → Lens: Post to dev.to
3. Wait 2h → HTTP Request → Lens: Post summary tweet on X
4. Wait 1d → HTTP Request → Lens: Cross-post to Substack
5. HTTP Request → Lens: Check engagement metrics on each platform
6. Output: Dashboard update with engagement data

**Use case:** Content marketing automation
**Revenue:** "Content Syndication" recipe

### 4. AI Studio Image Pipeline
**Trigger:** Webhook with image description
**Flow:**
1. n8n receives image request
2. HTTP Request → Lens: Navigate to AI Studio, select Nano Banana
3. HTTP Request → Lens: Submit prompt, wait for generation
4. HTTP Request → Lens: Extract generated image (base64 chunk transfer)
5. n8n: Save to local storage / upload to CDN / attach to email
6. Output: Image file + metadata

**Use case:** On-demand image generation without API keys
**Revenue:** "Free Image Gen" recipe

### 5. NotebookLM Audio Generator
**Trigger:** Webhook with source documents
**Flow:**
1. n8n receives document URLs or text
2. HTTP Request → Lens: Create NotebookLM notebook
3. HTTP Request → Lens: Add sources (paste text / add URLs)
4. HTTP Request → Lens: Generate Audio Overview
5. Wait for completion → Download audio file
6. Output: Podcast-style audio ready for distribution

**Use case:** Automated podcast creation from research docs
**Revenue:** "AI Podcast Factory" recipe

### 6. Competitor Monitoring
**Trigger:** Daily cron
**Flow:**
1. HTTP Request → Lens: Navigate to competitor pricing pages
2. n8n Code: Extract pricing data, compare with stored values
3. n8n IF: Price changed → Alert via Telegram
4. n8n IF: New feature detected → Log to spreadsheet
5. Optional: Route to Gemini for trend analysis

**Use case:** Market intelligence
**Revenue:** "Competitor Radar" recipe

### 7. Multi-Model Code Review
**Trigger:** GitHub webhook (new PR)
**Flow:**
1. n8n receives PR diff from GitHub
2. HTTP Request → Lens `/chat?model=claude` ("Review this diff for bugs")
3. HTTP Request → Lens `/chat?model=gemini` ("Review for performance")
4. HTTP Request → Lens `/chat?model=chatgpt` ("Review for security")
5. n8n Code: Merge reviews, format as PR comment
6. n8n GitHub: Post consolidated review comment

**Use case:** Free multi-model code review
**Revenue:** "AI Code Review Board" recipe

## Lens API Endpoints Needed

### Existing (working)
- `POST /chat` — Send prompt to model, get response
- `GET /health` — Container health check

### To Build
- `POST /email/inbox` — Read inbox (returns list of emails)
- `POST /email/send` — Compose and send email
- `POST /navigate` — Navigate to URL, return page content
- `POST /screenshot` — Capture current page as image
- `POST /image/generate` — AI Studio image generation
- `POST /notebook/create` — Create NotebookLM notebook
- `POST /notebook/audio` — Generate audio overview
- `GET /sessions` — List active browser sessions/tabs
- `POST /tab/open` — Open new tab to URL
- `POST /tab/close` — Close tab

## n8n Integration Method

### Option A: HTTP Request nodes (simplest)
- Each n8n node calls Lens REST API
- Works today with existing n8n on Omni
- No custom n8n nodes needed

### Option B: Custom n8n Community Node
- `n8n-nodes-chitin-lens` npm package
- Provides native Lens actions in n8n UI
- Better UX, autocomplete, credential management
- Higher effort but better product

### Option C: n8n + MCP
- Lens as MCP server
- n8n's AI Agent node connects via MCP
- Most flexible but requires MCP support in n8n

**Recommendation:** Start with Option A (HTTP), ship Option B when we have traction.

## Stitch Integration (Future)
Google Stitch uses Angular web components that resist CDP event injection.
**Solution:** AT-SPI (accessibility API) — exactly what Chitin Lens was designed for.
Once AT-SPI discovery works reliably, Stitch becomes:
- Text-to-UI design on demand
- Figma export for handoff to designers
- Automated mockup generation for client pitches

This is a killer demo: "Agent designs a mobile app UI from a text description and exports to Figma — no Figma subscription needed."

## Revenue Model

| Product | Price | Includes |
|---------|-------|----------|
| Chitin Lens (open source) | Free | Docker container + basic router |
| Vesper Blueprint | $29 | Setup guide + architecture patterns |
| Pro Recipes Bundle | $49 | 10+ n8n workflow templates with Lens |
| Chitin Cloud (future) | $X/mo | Hosted Lens + pre-configured n8n |

## Implementation Priority

1. **Now:** Build REST API endpoints for email, navigate, screenshot
2. **Week 1:** Create 3 working n8n workflow templates
3. **Week 2:** Record demo videos of each workflow
4. **Week 3:** Package as "Pro Recipes" and sell alongside Blueprint
5. **Month 2:** Build custom n8n community node

---

*Generated by Vesper 🌒 via Chitin Lens browser automation across AI Studio, NotebookLM, Gemini, ChatGPT, and Claude — February 24, 2026*
