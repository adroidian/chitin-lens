"""Scan the accessibility tree and print interesting nodes."""
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

INTERESTING = {"text", "entry", "password text", "push button", 
               "check box", "link", "heading", "label", "document web",
               "paragraph", "section", "form"}

def walk(node, depth=0, max_depth=8):
    if depth > max_depth:
        return
    try:
        name = node.get_name() or ""
        role = node.get_role_name()
        
        if role in INTERESTING or (name and len(name) > 2):
            indent = "  " * depth
            state_set = node.get_state_set()
            editable = state_set.contains(Atspi.StateType.EDITABLE)
            focusable = state_set.contains(Atspi.StateType.FOCUSABLE)
            flags = []
            if editable:
                flags.append("EDIT")
            if focusable:
                flags.append("FOCUS")
            flag_str = " [" + ",".join(flags) + "]" if flags else ""
            print(indent + role + ': "' + name + '"' + flag_str)
        
        for i in range(node.get_child_count()):
            walk(node.get_child_at_index(i), depth + 1, max_depth)
    except Exception:
        pass

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if app and "hrom" in (app.get_name() or ""):
        print("=== " + app.get_name() + " ===")
        walk(app, 0)
