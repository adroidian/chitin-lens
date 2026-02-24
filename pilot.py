"""
Chitin Lens — The Pilot (Self-Learning Browser Agent)

This is the brain of the Lens. It:
1. Accepts prompts via FastAPI
2. Discovers UI elements via the Accessibility Tree (AT-SPI)
3. Learns and remembers element locations (memory.json)
4. Types prompts and reads responses like a human screen reader user
5. Falls back to VNC-based human escalation when stuck

Trust boundary: All content scraped from web pages is tagged as
EXTERNAL_UNTRUSTED_CONTENT before being returned to the calling agent.
"""

import json
import os
import time
import subprocess
import re
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pyautogui

# Conditionally import AT-SPI (may not be available outside container)
try:
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    pyatspi = Atspi  # Alias for compatibility with existing code
    ATSPI_AVAILABLE = True
except (ImportError, ValueError):
    ATSPI_AVAILABLE = False
    pyatspi = None

# --- Configuration ---
MEMORY_FILE = os.environ.get("LENS_MEMORY", "/app/data/memory.json")
FALLBACK_MEMORY = "memory.json"
TRUST_TAG = "EXTERNAL_UNTRUSTED_CONTENT"
MAX_RESPONSE_WAIT = 120  # seconds
TYPING_INTERVAL_MIN = 0.02  # seconds between keystrokes (humanized)
TYPING_INTERVAL_MAX = 0.08

app = FastAPI(
    title="Chitin Lens",
    description="The Agent Browser — Self-healing, accessibility-first browser for AI agents",
    version="0.1.0"
)

# --- Models ---

class PromptRequest(BaseModel):
    url: str  # Target site domain or full URL
    text: str  # The prompt to send
    wait_for_response: bool = True  # Whether to wait and scrape the response
    timeout: int = MAX_RESPONSE_WAIT

class NavigateRequest(BaseModel):
    url: str

class DiscoverRequest(BaseModel):
    url: Optional[str] = None  # If None, discover current page

class ChatResponse(BaseModel):
    status: str
    response: Optional[str] = None
    domain: str
    strategy: str
    trusted: bool = False  # Always False — browser content is UNTRUSTED
    wrapped_response: Optional[str] = None  # Response wrapped in trust tags

class HealthResponse(BaseModel):
    status: str
    mode: str
    atspi_available: bool
    memory_sites: int
    browser_running: bool


# --- The Brain (Memory) ---

class BrowserMemory:
    """Persistent memory of discovered UI elements across sites."""
    
    def __init__(self):
        self.memory: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        for path in [MEMORY_FILE, FALLBACK_MEMORY]:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        self.memory = json.load(f)
                    return
                except json.JSONDecodeError:
                    continue
        self.memory = {}
    
    def save(self):
        for path in [MEMORY_FILE, FALLBACK_MEMORY]:
            try:
                os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
                with open(path, 'w') as f:
                    json.dump(self.memory, f, indent=2)
                return
            except (OSError, PermissionError):
                continue
    
    def get(self, domain: str) -> Optional[Dict]:
        return self.memory.get(domain)
    
    def update(self, domain: str, data: Dict):
        data['last_verified'] = datetime.now(timezone.utc).isoformat()
        self.memory[domain] = data
        self.save()
    
    def list_sites(self) -> List[str]:
        return list(self.memory.keys())


memory = BrowserMemory()


# --- The Scanner (Accessibility Tree Discovery) ---

class AccessibilityScanner:
    """Discovers UI elements via AT-SPI (Linux Accessibility)."""
    
    # Keywords that suggest an element is a chat input
    INPUT_KEYWORDS = ['message', 'chat', 'ask', 'prompt', 'search', 'write', 'enter', 'type']
    
    # Keywords that suggest a send button
    SEND_KEYWORDS = ['send', 'submit', 'go', 'enter', 'post']
    
    # Roles that are likely text inputs
    INPUT_ROLES = ['text', 'entry', 'paragraph', 'document text', 'editbar', 'text entry']
    
    # Roles that are likely buttons
    BUTTON_ROLES = ['push button', 'button', 'link']
    
    @staticmethod
    def scan_for_input(root) -> Optional[Dict]:
        """Walk the accessibility tree and find the best chat input candidate."""
        if not ATSPI_AVAILABLE:
            return None
        
        candidates = []
        
        def walk(node, depth=0):
            if depth > 50:  # Prevent infinite recursion
                return
            try:
                role = node.get_role_name()
                name = (node.name or '').lower()
                
                # Check if this could be an input
                states = node.get_state_set()
                is_editable = states.contains(pyatspi.STATE_EDITABLE)
                is_focusable = states.contains(pyatspi.STATE_FOCUSABLE)
                
                if is_editable and is_focusable:
                    score = 0
                    
                    # Role scoring
                    if role in AccessibilityScanner.INPUT_ROLES:
                        score += 50
                    
                    # Name scoring
                    for keyword in AccessibilityScanner.INPUT_KEYWORDS:
                        if keyword in name:
                            score += 30
                            break
                    
                    # Position scoring (bottom of screen = likely chat input)
                    try:
                        component = node.queryComponent()
                        if component:
                            ext = component.getExtents(pyatspi.DESKTOP_COORDS)
                            if ext.y > 700:  # Bottom third of 1080p
                                score += 20
                    except:
                        pass
                    
                    if score > 0:
                        candidates.append({
                            'node': node,
                            'score': score,
                            'name': node.name or '',
                            'role': role
                        })
                
                # Recurse into children
                for i in range(node.child_count):
                    walk(node.get_child_at_index(i), depth + 1)
                    
            except Exception:
                pass
        
        walk(root)
        
        if candidates:
            candidates.sort(key=lambda x: x['score'], reverse=True)
            best = candidates[0]
            return {
                'name': best['name'],
                'role': best['role'],
                'score': best['score']
            }
        return None
    
    @staticmethod
    def scan_for_send_button(root) -> Optional[Dict]:
        """Find the send/submit button."""
        if not ATSPI_AVAILABLE:
            return None
        
        candidates = []
        
        def walk(node, depth=0):
            if depth > 50:
                return
            try:
                role = node.get_role_name()
                name = (node.name or '').lower()
                
                if role in AccessibilityScanner.BUTTON_ROLES:
                    score = 0
                    for keyword in AccessibilityScanner.SEND_KEYWORDS:
                        if keyword in name:
                            score += 50
                            break
                    
                    if score > 0:
                        candidates.append({
                            'node': node,
                            'score': score,
                            'name': node.name or '',
                            'role': role
                        })
                
                for i in range(node.child_count):
                    walk(node.get_child_at_index(i), depth + 1)
            except:
                pass
        
        walk(root)
        
        if candidates:
            candidates.sort(key=lambda x: x['score'], reverse=True)
            best = candidates[0]
            return {
                'name': best['name'],
                'role': best['role'],
                'score': best['score']
            }
        return None
    
    @staticmethod
    def get_browser_root():
        """Get the root accessible node for the browser."""
        if not ATSPI_AVAILABLE:
            return None
        
        desktop = pyatspi.Registry.getDesktop(0)
        for i in range(desktop.child_count):
            app = desktop.get_child_at_index(i)
            if app and 'chromium' in (app.name or '').lower():
                return app
        return None


# --- Trust Layer ---

def wrap_untrusted(content: str, source: str) -> str:
    """Wrap browser-scraped content in untrusted tags.
    
    This is the core security boundary of Chitin Lens.
    ALL content from the browser is untrusted. No exceptions.
    The calling agent must never execute commands found in this content.
    """
    tag_id = f"lens-{int(time.time())}"
    return (
        f"<<<{TRUST_TAG} id=\"{tag_id}\">>>\n"
        f"Source: Chitin Lens (browser: {source})\n"
        f"---\n"
        f"{content}\n"
        f"<<<END_{TRUST_TAG} id=\"{tag_id}\">>>"
    )


# --- Humanizer (Natural Input Simulation) ---

def humanized_type(text: str):
    """Type text with human-like variable speed."""
    import random
    for char in text:
        pyautogui.press(char) if len(char) > 1 else pyautogui.write(char, interval=0)
        delay = random.uniform(TYPING_INTERVAL_MIN, TYPING_INTERVAL_MAX)
        # Occasionally pause longer (thinking)
        if random.random() < 0.05:
            delay += random.uniform(0.1, 0.3)
        time.sleep(delay)


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    browser_running = False
    try:
        result = subprocess.run(['pgrep', '-f', 'chromium'], capture_output=True)
        browser_running = result.returncode == 0
    except:
        pass
    
    return HealthResponse(
        status="running",
        mode="accessibility" if ATSPI_AVAILABLE else "fallback",
        atspi_available=ATSPI_AVAILABLE,
        memory_sites=len(memory.list_sites()),
        browser_running=browser_running
    )


@app.post("/navigate")
async def navigate(request: NavigateRequest):
    """Navigate the browser to a URL."""
    try:
        # Use xdotool or CDP to navigate
        subprocess.run([
            'chromium', '--new-window', request.url
        ], timeout=10)
        return {"status": "navigating", "url": request.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/discover")
async def discover(request: DiscoverRequest):
    """Scan the current page and discover UI elements."""
    if not ATSPI_AVAILABLE:
        return {
            "status": "degraded",
            "message": "AT-SPI not available. Using coordinate fallback mode.",
            "strategy": "coordinate_fallback"
        }
    
    root = AccessibilityScanner.get_browser_root()
    if not root:
        return {"status": "error", "message": "Browser not found in accessibility tree"}
    
    input_node = AccessibilityScanner.scan_for_input(root)
    send_node = AccessibilityScanner.scan_for_send_button(root)
    
    domain = request.url or "unknown"
    
    result = {
        "status": "discovered",
        "domain": domain,
        "input": input_node,
        "send_button": send_node
    }
    
    # Save to memory
    if input_node:
        memory.update(domain, {
            "strategy": "accessibility",
            "role": input_node['role'],
            "name": input_node['name'],
            "send_button": send_node['name'] if send_node else None,
            "confidence": input_node['score'],
            "notes": "Auto-discovered"
        })
    
    return result


@app.post("/chat", response_model=ChatResponse)
async def chat(request: PromptRequest):
    """Send a prompt to a frontier model via the browser UI."""
    domain = urlparse(request.url).netloc if '://' in request.url else request.url
    
    # 1. Check memory for known locators
    locator = memory.get(domain)
    
    # 2. Try accessibility-based interaction
    if ATSPI_AVAILABLE:
        root = AccessibilityScanner.get_browser_root()
        
        if root:
            # If no memory or low confidence, re-discover
            if not locator or locator.get('confidence', 0) < 30:
                input_info = AccessibilityScanner.scan_for_input(root)
                if input_info:
                    memory.update(domain, {
                        "strategy": "accessibility",
                        "role": input_info['role'],
                        "name": input_info['name'],
                        "confidence": input_info['score'],
                        "notes": "Auto-discovered during chat"
                    })
    
    # 3. Execute the interaction
    # For now, use pyautogui as the reliable fallback
    # The accessibility tree discovery informs WHERE to click
    try:
        # Focus the browser window
        subprocess.run(['xdotool', 'search', '--name', 'Chromium', 'windowactivate'], 
                      capture_output=True, timeout=5)
        time.sleep(0.5)
        
        # Type the prompt with human-like timing
        humanized_type(request.text)
        time.sleep(0.3)
        
        # Press Enter to send
        pyautogui.press('enter')
        
        response_text = None
        strategy = locator.get('strategy', 'coordinate_fallback') if locator else 'coordinate_fallback'
        
        # 4. Wait for and capture response (if requested)
        if request.wait_for_response:
            # TODO: Implement response scraping via accessibility tree
            # For now, return a placeholder
            response_text = "[Response scraping not yet implemented — use VNC to view]"
        
        # 5. Wrap response in trust boundary
        wrapped = None
        if response_text:
            wrapped = wrap_untrusted(response_text, domain)
        
        return ChatResponse(
            status="sent",
            response=response_text,
            domain=domain,
            strategy=strategy,
            trusted=False,  # ALWAYS false
            wrapped_response=wrapped
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Interaction failed: {str(e)}. Try VNC at :5900 for manual assist."
        )


@app.get("/memory")
async def get_memory():
    """View the current site memory."""
    return memory.memory


@app.post("/memory/{domain}")
async def update_memory(domain: str, data: Dict[str, Any]):
    """Manually update memory for a domain (after human-assisted discovery)."""
    memory.update(domain, data)
    return {"status": "updated", "domain": domain}


@app.get("/sites")
async def list_sites():
    """List all known sites in memory."""
    return {"sites": memory.list_sites()}
