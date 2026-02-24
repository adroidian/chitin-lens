#!/usr/bin/env python3
"""
Chitin Lens — Multi-Model Router

Routes prompts to frontier models through their web UIs.
Manages multiple tabs, injects agent context, extracts responses.

Architecture:
    [Agent] → POST /route → Router → [Gemini|ChatGPT|Claude tab] → response

Usage:
    POST /route {"prompt": "...", "model": "gemini", "context_files": ["SOUL.md"]}
    POST /route {"prompt": "...", "model": "auto"}  # Router picks best model
    GET  /models  # List available models and status
"""

import json
import time
import os
import urllib.request
import websocket
from typing import Optional, Dict, List
from dataclasses import dataclass

# --- Tab Registry ---

@dataclass
class ModelTab:
    name: str
    tab_id: str
    ws_url: str
    input_method: str  # "textarea" or "contenteditable" 
    input_selector: str
    send_method: str  # "enter", "button"
    send_selector: Optional[str]
    response_selector: str
    new_chat_selector: Optional[str]
    strengths: List[str]  # What this model is good at
    
MODELS = {
    "gemini": ModelTab(
        name="Gemini 3.1 Pro",
        tab_id="", ws_url="",
        input_method="contenteditable",
        input_selector='[contenteditable="true"][aria-label*="prompt" i]',
        send_method="enter",
        send_selector=None,
        response_selector=".response-content",
        new_chat_selector='a[href="/app"]',
        strengths=["long_context", "multimodal", "google_integration", "fast"]
    ),
    "chatgpt": ModelTab(
        name="ChatGPT (GPT-5.2)",
        tab_id="", ws_url="",
        input_method="contenteditable",
        input_selector='#prompt-textarea, [data-testid="chat-input"], [contenteditable="true"]',
        send_method="button",
        send_selector='[data-testid="send-button"], button[aria-label="Send prompt"], button[aria-label*="Send"]',
        response_selector="[data-message-author-role='assistant'], .markdown, .agent-turn",
        new_chat_selector='a[href="/"]',
        strengths=["code", "reasoning", "instruction_following", "plugins"]
    ),
    "claude": ModelTab(
        name="Claude Opus 4.6",
        tab_id="", ws_url="",
        input_method="contenteditable",
        input_selector='[data-testid="chat-input"], [contenteditable="true"]',
        send_method="button",
        send_selector='button[aria-label="Send message"]',
        response_selector='[data-is-streaming], [data-testid="chat-message-content"], .font-claude-message',
        new_chat_selector='a[href="/new"]',
        strengths=["writing", "analysis", "safety", "nuance", "long_output"]
    ),
}

# Auto-routing rules
ROUTE_RULES = {
    "code": "chatgpt",
    "debug": "chatgpt",
    "write": "claude",
    "essay": "claude",
    "analyze": "claude",
    "review": "claude",
    "research": "gemini",
    "search": "gemini",
    "summarize": "gemini",
    "math": "gemini",
    "default": "gemini",
}


class LensRouter:
    def __init__(self):
        self.cdp_host = "127.0.0.1"
        self.cdp_port = 9222
        self.context_dir = "/app/context"  # Mounted workspace files
        self.connections: Dict[str, websocket.WebSocket] = {}
        
    def discover_tabs(self):
        """Map running tabs to model registry."""
        tabs = json.loads(urllib.request.urlopen(
            f"http://{self.cdp_host}:{self.cdp_port}/json/list"
        ).read())
        
        for tab in tabs:
            if tab['type'] != 'page': continue
            url = tab['url'].lower()
            
            if 'gemini.google.com' in url:
                MODELS['gemini'].tab_id = tab['id']
                MODELS['gemini'].ws_url = tab['webSocketDebuggerUrl']
            elif 'chatgpt.com' in url or 'chat.openai.com' in url:
                MODELS['chatgpt'].tab_id = tab['id']
                MODELS['chatgpt'].ws_url = tab['webSocketDebuggerUrl']
            elif 'claude.ai' in url:
                MODELS['claude'].tab_id = tab['id']
                MODELS['claude'].ws_url = tab['webSocketDebuggerUrl']
        
        return {k: bool(v.tab_id) for k, v in MODELS.items()}
    
    def _connect(self, model_key: str) -> websocket.WebSocket:
        """Get or create websocket connection to a model's tab."""
        model = MODELS[model_key]
        if not model.ws_url:
            self.discover_tabs()
        if not model.ws_url:
            raise Exception(f"No tab found for {model_key}")
        
        if model_key in self.connections:
            try:
                self.connections[model_key].ping()
                return self.connections[model_key]
            except:
                pass
        
        ws = websocket.create_connection(model.ws_url)
        ws.settimeout(30)
        self.connections[model_key] = ws
        return ws
    
    def _cdp(self, ws, method, params=None):
        """Send CDP command and get response."""
        import random
        msg_id = random.randint(10000, 99999)
        ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
        while True:
            r = json.loads(ws.recv())
            if r.get("id") == msg_id:
                return r
    
    def _val(self, r):
        return r.get("result", {}).get("result", {}).get("value")
    
    def auto_route(self, prompt: str) -> str:
        """Pick the best model based on prompt content."""
        prompt_lower = prompt.lower()
        for keyword, model in ROUTE_RULES.items():
            if keyword in prompt_lower:
                return model
        return ROUTE_RULES["default"]
    
    def build_context_preamble(self, context_files: List[str] = None) -> str:
        """Build a context injection preamble from workspace files."""
        if not context_files:
            context_files = ["SOUL.md", "USER.md"]
        
        preamble_parts = []
        preamble_parts.append("=== AGENT CONTEXT (from Vesper's workspace) ===")
        
        for filename in context_files:
            # Check both mounted context dir and local
            for base in [self.context_dir, "/app/data/context", "."]:
                path = os.path.join(base, filename)
                if os.path.exists(path):
                    try:
                        with open(path) as f:
                            content = f.read()[:3000]  # Cap at 3k per file
                        preamble_parts.append(f"\n--- {filename} ---\n{content}")
                    except:
                        pass
                    break
        
        preamble_parts.append("\n=== END CONTEXT ===\n")
        return "\n".join(preamble_parts)
    
    def new_chat(self, model_key: str):
        """Start a new chat in the model's tab."""
        model = MODELS[model_key]
        ws = self._connect(model_key)
        
        if model.new_chat_selector:
            self._cdp(ws, "Runtime.evaluate", {"expression": f"""
                document.querySelector('{model.new_chat_selector}')?.click()
            """})
            time.sleep(2)
    
    def send_prompt(self, model_key: str, prompt: str, context_files: List[str] = None, 
                    new_chat: bool = True, inject_context: bool = True) -> dict:
        """Send a prompt to a model and get the response."""
        model = MODELS[model_key]
        ws = self._connect(model_key)
        
        # Start fresh conversation if requested
        if new_chat:
            self.new_chat(model_key)
        
        # Build full prompt with context
        full_prompt = ""
        if inject_context and context_files:
            full_prompt = self.build_context_preamble(context_files) + "\n\n"
        full_prompt += prompt
        
        # Type the prompt
        if model.input_method == "textarea":
            # For textarea: focus and set value
            escaped = full_prompt.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
            self._cdp(ws, "Runtime.evaluate", {"expression": f"""
                (() => {{
                    const el = document.querySelector('{model.input_selector}');
                    if (!el) return 'NO_INPUT';
                    el.focus();
                    if (el.tagName === 'TEXTAREA') {{
                        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                        setter.call(el, `{escaped}`);
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }} else {{
                        el.innerText = `{escaped}`;
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    }}
                    return 'OK';
                }})()
            """})
        else:
            # For contenteditable (Gemini): use keyboard events
            self._cdp(ws, "Runtime.evaluate", {"expression": f"""
                document.querySelector('{model.input_selector}')?.focus()
            """})
            time.sleep(0.3)
            for char in full_prompt:
                self._cdp(ws, "Input.dispatchKeyEvent", {
                    "type": "keyDown", "key": char, "text": char
                })
                self._cdp(ws, "Input.dispatchKeyEvent", {
                    "type": "keyUp", "key": char
                })
        
        time.sleep(0.5)
        
        # Send
        if model.send_method == "enter":
            self._cdp(ws, "Input.dispatchKeyEvent", {
                "type": "keyDown", "key": "Enter", "code": "Enter", 
                "windowsVirtualKeyCode": 13
            })
            self._cdp(ws, "Input.dispatchKeyEvent", {
                "type": "keyUp", "key": "Enter", "code": "Enter",
                "windowsVirtualKeyCode": 13
            })
        else:
            self._cdp(ws, "Runtime.evaluate", {"expression": f"""
                (() => {{
                    const btn = document.querySelector('{model.send_selector}');
                    if (btn) {{ btn.click(); return 'CLICKED'; }}
                    return 'NO_BUTTON';
                }})()
            """})
        
        # Wait for response
        start = time.time()
        max_wait = 120
        last_len = 0
        stable_count = 0
        
        while time.time() - start < max_wait:
            time.sleep(2)
            
            r = self._cdp(ws, "Runtime.evaluate", {"expression": f"""
                (() => {{
                    const responses = document.querySelectorAll('{model.response_selector}');
                    const last = responses.length ? responses[responses.length - 1] : null;
                    const text = last?.innerText || '';
                    
                    // Check if still generating
                    const stopBtn = document.querySelector('[aria-label*="Stop"], button[class*="stop"]');
                    const generating = !!stopBtn;
                    
                    return {{ length: text.length, generating: generating }};
                }})()
            """, "returnByValue": True})
            
            state = self._val(r) or {}
            current_len = state.get("length", 0)
            generating = state.get("generating", False)
            
            # Response complete when: not generating AND text is stable AND has content
            if not generating and current_len > 0:
                if current_len == last_len:
                    stable_count += 1
                    if stable_count >= 2:
                        break
                else:
                    stable_count = 0
            
            last_len = current_len
        
        # Extract response
        r = self._cdp(ws, "Runtime.evaluate", {"expression": f"""
            (() => {{
                const responses = document.querySelectorAll('{model.response_selector}');
                const last = responses.length ? responses[responses.length - 1] : null;
                return last?.innerText || 'NO_RESPONSE';
            }})()
        """})
        response_text = self._val(r) or "NO_RESPONSE"
        
        elapsed = round(time.time() - start, 1)
        
        return {
            "model": model.name,
            "model_key": model_key,
            "response": response_text,
            "chars": len(response_text),
            "elapsed_seconds": elapsed,
            "context_injected": bool(context_files) and inject_context,
            "trust": "UNTRUSTED"
        }
    
    def status(self) -> dict:
        """Get status of all model tabs."""
        tab_status = self.discover_tabs()
        return {
            "models": {
                k: {
                    "name": v.name,
                    "available": bool(v.tab_id),
                    "strengths": v.strengths,
                    "tab_id": v.tab_id[:12] if v.tab_id else None
                }
                for k, v in MODELS.items()
            },
            "total_available": sum(1 for v in tab_status.values() if v),
            "routing_rules": ROUTE_RULES
        }


# --- CLI for testing ---
if __name__ == "__main__":
    import sys
    router = LensRouter()
    
    if len(sys.argv) < 2:
        print(json.dumps(router.status(), indent=2))
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "status":
        print(json.dumps(router.status(), indent=2))
    
    elif cmd == "route":
        model = sys.argv[2] if len(sys.argv) > 2 else "auto"
        prompt = sys.argv[3] if len(sys.argv) > 3 else "Hello! What model are you? Reply in one sentence."
        context = sys.argv[4].split(",") if len(sys.argv) > 4 else None
        
        if model == "auto":
            model = router.auto_route(prompt)
            print(f"Auto-routed to: {model}")
        
        result = router.send_prompt(model, prompt, context_files=context)
        print(json.dumps(result, indent=2))
    
    elif cmd == "all":
        # Send to ALL models and compare
        prompt = sys.argv[2] if len(sys.argv) > 2 else "What model are you? Reply in exactly one sentence."
        for model_key in ["gemini", "chatgpt", "claude"]:
            if MODELS[model_key].tab_id or router.discover_tabs().get(model_key):
                print(f"\n--- {model_key.upper()} ---")
                try:
                    result = router.send_prompt(model_key, prompt, new_chat=True, inject_context=False)
                    print(f"  Response ({result['elapsed_seconds']}s): {result['response'][:200]}")
                except Exception as e:
                    print(f"  ERROR: {e}")
