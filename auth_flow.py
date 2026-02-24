#!/usr/bin/env python3
"""
Chitin Lens — Universal Auth Flow
Self-discovering login handler. Probes the DOM for auth fields,
maps them, saves to memory.json, and executes login.

Usage (inside container):
    python3 lens-auth-flow.py <url> <username> <password>
"""
import json, time, sys, os, urllib.request, websocket

MEMORY_FILE = "/app/data/memory.json"

# --- Memory ---
def load_memory():
    try:
        with open(MEMORY_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_memory(mem):
    os.makedirs(os.path.dirname(MEMORY_FILE) or '.', exist_ok=True)
    with open(MEMORY_FILE, 'w') as f:
        json.dump(mem, f, indent=2)

# --- CDP Helpers ---
def connect_to_page(url_filter=None):
    tabs = json.loads(urllib.request.urlopen("http://127.0.0.1:9222/json/list").read())
    page = None
    if url_filter:
        page = next((t for t in tabs if t['type'] == 'page' and url_filter in t.get('url', '')), None)
    if not page:
        page = next(t for t in tabs if t['type'] == 'page')
    ws = websocket.create_connection(page['webSocketDebuggerUrl'])
    ws.settimeout(30)
    return ws, page

msg_id = 0
def cdp(ws, method, params=None):
    global msg_id; msg_id += 1
    ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        r = json.loads(ws.recv())
        if r.get("id") == msg_id: return r

def val(r):
    return r.get("result", {}).get("result", {}).get("value")

# --- Phase 1: Discover Auth Fields ---
def discover_auth_fields(ws):
    """Scan page for username/email and password fields. Returns field map."""
    r = cdp(ws, "Runtime.evaluate", {"expression": """
    (() => {
        const inputs = Array.from(document.querySelectorAll('input')).filter(i => i.offsetParent !== null);
        const fields = inputs.map(i => ({
            id: i.id,
            name: i.name,
            type: i.type,
            placeholder: i.placeholder,
            ariaLabel: i.getAttribute('aria-label'),
            autocomplete: i.getAttribute('autocomplete'),
            // Build best selector
            selector: i.id ? '#' + i.id : 
                      i.name ? 'input[name="' + i.name + '"]' :
                      i.type === 'password' ? 'input[type="password"]' :
                      null
        }));
        
        // Classify fields
        const result = { username: null, password: null, submit: null };
        
        // Password is easy — type="password"
        const pwField = fields.find(f => f.type === 'password');
        if (pwField) result.password = pwField;
        
        // Username/email: type=email, or type=text that's NOT a search/hidden field
        // Prefer: autocomplete="username"/"email" > type="email" > id contains user/email/login > first visible text input
        const candidates = fields.filter(f => f.type !== 'password' && f.type !== 'hidden' && f.type !== 'checkbox' && f.type !== 'submit');
        
        const byAutocomplete = candidates.find(f => ['username', 'email'].includes(f.autocomplete));
        const byType = candidates.find(f => f.type === 'email');
        const byId = candidates.find(f => /user|email|login|account/i.test(f.id + f.name + (f.placeholder || '')));
        const fallback = candidates[0];
        
        result.username = byAutocomplete || byType || byId || fallback;
        
        // Find submit button
        const btn = document.querySelector('button[type="submit"]') || 
                    Array.from(document.querySelectorAll('button')).find(b => 
                        /sign.?in|log.?in|submit|continue/i.test(b.textContent));
        if (btn) {
            result.submit = {
                selector: btn.type === 'submit' ? 'button[type="submit"]' : null,
                text: btn.textContent.trim().substring(0, 30)
            };
        }
        
        return result;
    })()
    """, "returnByValue": True})
    
    return val(r)

# --- Phase 2: Fill and Submit ---
def fill_field(ws, selector, value):
    """Fill a field using native setter (works with React/Angular/Vue)."""
    escaped_val = value.replace("\\", "\\\\").replace("'", "\\'")
    r = cdp(ws, "Runtime.evaluate", {"expression": f"""
    (() => {{
        const el = document.querySelector('{selector}');
        if (!el) return 'NOT_FOUND: {selector}';
        el.focus();
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(el, '{escaped_val}');
        el.dispatchEvent(new Event('input', {{bubbles: true}}));
        el.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'OK: ' + el.value.length + ' chars';
    }})()
    """})
    return val(r)

def click_submit(ws, selector=None):
    sel = selector or 'button[type="submit"]'
    r = cdp(ws, "Runtime.evaluate", {"expression": f"""
    (() => {{
        const btn = document.querySelector('{sel}');
        if (!btn) return 'NO_BUTTON';
        btn.click();
        return 'CLICKED: ' + btn.textContent.trim();
    }})()
    """})
    return val(r)

def check_result(ws):
    """Check post-login state."""
    time.sleep(10)
    r = cdp(ws, "Runtime.evaluate", {"expression": "document.title + ' | ' + location.href"})
    page = val(r)
    
    r = cdp(ws, "Runtime.evaluate", {"expression": """
    (() => {
        const alerts = document.querySelectorAll('[role="alert"], [class*="error"], [class*="notification-danger"]');
        const errs = Array.from(alerts).map(a => a.textContent.trim()).filter(t => t.length > 3 && t.length < 200);
        return errs.length ? errs.join(' | ') : null;
    })()
    """})
    errors = val(r)
    
    return page, errors

# --- Main Flow ---
def login(url, username, password):
    from urllib.parse import urlparse
    domain = urlparse(url).netloc
    memory = load_memory()
    
    ws, tab = connect_to_page()
    
    # Navigate if needed
    if domain not in tab.get('url', ''):
        print(f"Navigating to {url}...")
        cdp(ws, "Page.enable")
        cdp(ws, "Page.navigate", {"url": url})
        time.sleep(6)
    
    # Check if already authenticated (no login form = probably logged in)
    already_in = val(cdp(ws, "Runtime.evaluate", {"expression": """
    (() => {
        const pwField = document.querySelector('input[type="password"]');
        const url = location.href;
        // If no password field and URL doesn't contain login/signin/auth paths, likely authenticated
        if (!pwField && !/login|signin|sign-in|auth|account/.test(url)) return true;
        return false;
    })()
    """}))
    if already_in:
        print(f"Already authenticated on {domain}! Current page: {val(cdp(ws, 'Runtime.evaluate', {'expression': 'document.title'}))}")
        ws.close()
        return True
    
    # Check if we have a cached auth map for this domain
    site_mem = memory.get(domain, {})
    auth_map = site_mem.get("auth_fields")
    
    if auth_map:
        print(f"Using cached auth map for {domain}")
    else:
        print(f"Discovering auth fields for {domain}...")
        auth_map = discover_auth_fields(ws)
        if not auth_map or not auth_map.get('username') or not auth_map.get('password'):
            print(f"FAILED: Could not discover auth fields. Found: {json.dumps(auth_map, indent=2)}")
            ws.close()
            return False
        
        # Save to memory
        site_mem["auth_fields"] = {
            "username_selector": auth_map["username"]["selector"],
            "password_selector": auth_map["password"]["selector"],
            "submit_selector": auth_map["submit"]["selector"] if auth_map.get("submit") else "button[type='submit']",
            "username_field_id": auth_map["username"].get("id"),
            "discovered": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        memory[domain] = site_mem
        save_memory(memory)
        print(f"Auth map saved to memory: {json.dumps(site_mem['auth_fields'], indent=2)}")
    
    # Get selectors (from cache or fresh discovery)
    if isinstance(auth_map, dict) and "username_selector" in auth_map:
        # Cached format
        u_sel = auth_map["username_selector"]
        p_sel = auth_map["password_selector"]
        s_sel = auth_map.get("submit_selector", "button[type='submit']")
    else:
        # Fresh discovery format
        u_sel = auth_map["username"]["selector"]
        p_sel = auth_map["password"]["selector"]
        s_sel = auth_map["submit"]["selector"] if auth_map.get("submit") else "button[type='submit']"
    
    # Execute login
    print(f"Filling username ({u_sel})...")
    r = fill_field(ws, u_sel, username)
    print(f"  {r}")
    time.sleep(0.3)
    
    print(f"Filling password ({p_sel})...")
    r = fill_field(ws, p_sel, password)
    print(f"  {r}")
    time.sleep(0.3)
    
    print(f"Submitting ({s_sel})...")
    r = click_submit(ws, s_sel)
    print(f"  {r}")
    
    print("Checking result...")
    page, errors = check_result(ws)
    print(f"Page: {page}")
    if errors:
        print(f"ERRORS: {errors}")
        # Invalidate cached auth map on error
        if "auth_fields" in site_mem:
            del site_mem["auth_fields"]
            memory[domain] = site_mem
            save_memory(memory)
            print("Cleared cached auth map (will re-discover next time)")
    else:
        # Update last successful login
        site_mem["last_login"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        site_mem["last_login_page"] = page
        memory[domain] = site_mem
        save_memory(memory)
        print("Login successful! Memory updated.")
    
    ws.close()
    return errors is None

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <url> <username> <password>")
        sys.exit(1)
    
    success = login(sys.argv[1], sys.argv[2], sys.argv[3])
    sys.exit(0 if success else 1)
