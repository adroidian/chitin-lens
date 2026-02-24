"""Deep scan the accessibility tree — find form elements."""
import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi

def walk(node, depth=0, max_depth=15):
    if depth > max_depth:
        return
    try:
        name = node.get_name() or ""
        role = node.get_role_name()
        state_set = node.get_state_set()
        editable = state_set.contains(Atspi.StateType.EDITABLE)
        focusable = state_set.contains(Atspi.StateType.FOCUSABLE)
        
        # Print everything with a name, or editable/focusable items
        if name or editable or role in ("entry", "password text", "text", "push button", 
                                         "check box", "form", "heading", "link",
                                         "document web", "section"):
            indent = "  " * depth
            flags = []
            if editable: flags.append("EDIT")
            if focusable: flags.append("FOCUS")
            flag_str = " [" + ",".join(flags) + "]" if flags else ""
            children = node.get_child_count()
            cc = " (" + str(children) + " children)" if children > 0 else ""
            print(indent + role + ': "' + name[:60] + '"' + flag_str + cc)
        
        for i in range(node.get_child_count()):
            walk(node.get_child_at_index(i), depth + 1, max_depth)
    except Exception as e:
        pass

desktop = Atspi.get_desktop(0)
for i in range(desktop.get_child_count()):
    app = desktop.get_child_at_index(i)
    if app and "hrom" in (app.get_name() or ""):
        # Find the document web node and scan deep
        def find_doc(node, d=0):
            if d > 10:
                return None
            try:
                if node.get_role_name() == "document web":
                    return node
                for j in range(node.get_child_count()):
                    found = find_doc(node.get_child_at_index(j), d+1)
                    if found:
                        return found
            except:
                pass
            return None
        
        doc = find_doc(app)
        if doc:
            print("=== Document: " + (doc.get_name() or "unknown") + " ===")
            walk(doc, 0, 15)
        else:
            print("No document web node found")
