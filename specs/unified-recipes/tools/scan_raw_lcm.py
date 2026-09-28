"""Scan harvested recipe sources for raw LibLCM access; classify vs flexicon bridge index."""
import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LIB = Path(r"C:\Github\MCPlayground\.claude\skills\flex-parse-fixup\scripts\lib")
IDX = Path(r"C:\Github\FlexToolsMCP\src\flextoolsmcp\index")
SCRIPTS = {
    "candidates.py": "parser-coverage", "lexicon_lookup.py": "lexicon-form-lookup",
    "entry_detail.py": "entry-parser-detail", "wordform_analyses.py": "wordform-analyses",
    "allomorph_refs.py": "form-usage-before-edit", "templates_slots_envs.py": "affix-templates-and-slots",
    "phon_rules.py": "phonological-rules", "find_variants.py": "wordform-case-variants",
    "w_create_entries.py": "create-entries-idempotent", "w_create_stem_like.py": "create-entry-like-comparator",
    "w_set_allomorph_env.py": "set-allomorph-environments", "w_add_affix.py": "add-inflectional-affix",
    "w_add_allomorph.py": "add-allomorph",
}

lcm = json.load(open(IDX / "liblcm" / "liblcm_api_v11.0.0.json", encoding="utf-8"))["entities"]
lcm_members = defaultdict(set)  # member name -> interfaces declaring it
for ename, e in lcm.items():
    for p in e.get("properties", []) or []:
        if p.get("name"):
            lcm_members[p["name"]].add(ename)
    for m in e.get("methods", []) or []:
        if m.get("name"):
            lcm_members[m["name"]].add(ename)

bridge = json.load(open(IDX / "python" / "flexicon_lcm_bridge_v4.11.0.json", encoding="utf-8"))["by_method"]
prop_to_fx = defaultdict(set)
BAD = re.compile(r"\.(Duplicate|Delete|__\w+__|Copy\w*|_\w+)$")
for meth, v in bridge.items():
    if BAD.search(meth):
        continue
    props = set(v.get("properties_accessed", []) or []) | set((v.get("inline") or {}).get("properties_accessed", []) or [])
    for p in props:
        prop_to_fx[p.split(" ")[0]].add(meth)

def rank(ms):
    def k(m):
        n = m.split(".")[1]
        return (0 if re.match(r"(Get|Find|Is|Has)", n) else 1 if re.match(r"(Add|Set|Remove|Create)", n) else 2, m)
    return sorted(ms, key=k)

FX_ACCESSORS = set()
fp = json.load(open(IDX / "python" / "flexicon_api_v4.11.0.json", encoding="utf-8"))["entities"].get("FLExProject", {})
for p in fp.get("properties", []) or []:
    FX_ACCESSORS.add(p.get("name"))
fx_project_methods = {m.get("name") for m in fp.get("methods", []) or []}

GENERIC = {"Text", "Count", "Name", "Add", "Remove", "Contains", "ToString", "Clear", "Insert", "Item"}

def is_flexicon_chain(node):
    # project.<Accessor>.<Method> or project.<Method>
    n = node
    parts = []
    while isinstance(n, ast.Attribute):
        parts.append(n.attr)
        n = n.value
    if isinstance(n, ast.Name) and n.id == "project":
        parts.reverse()
        if parts and parts[0] == "project":
            return False
        return True
    return False

rows = defaultdict(lambda: {"kind": "", "recipes": set(), "lines": []})
for fname, rid in SCRIPTS.items():
    src = (LIB / fname).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        key = kind = None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and re.match(r"^I[A-Z]\w+$", node.func.id):
            key, kind = f"cast {node.func.id}(...)", "cast"
        elif isinstance(node, ast.Attribute):
            if is_flexicon_chain(node):
                continue
            a = node.attr
            if isinstance(node.value, ast.Name) and node.value.id == "project" and a == "project":
                key, kind = "project.project", "escape"
            elif a in ("ServiceLocator", "LangProject"):
                key, kind = a, "escape"
            elif a == "ClassName":
                key, kind = "ClassName", "dispatch"
            elif a in lcm_members and a not in GENERIC:
                key, kind = a, "member"
            elif re.search(r"(OA|OS|OC|RA|RS|RC)$", a):
                key, kind = a, "member"
        if key:
            r = rows[key]
            r["kind"] = kind
            r["recipes"].add(rid)
            r["lines"].append(f"{fname}:{node.lineno}")

out = []
for key, r in rows.items():
    prop = key.split(" ")[-1] if r["kind"] == "member" else None
    fx = rank(prop_to_fx.get(prop, set()))[:4] if prop else []
    out.append({
        "access": key, "kind": r["kind"], "recipes": sorted(r["recipes"]),
        "declared_on": sorted(lcm_members.get(prop, []))[:4] if prop else [],
        "flexicon_candidates": fx, "sites": r["lines"],
    })
out.sort(key=lambda x: (x["kind"], x["access"]))
json.dump(out, sys.stdout, indent=1)
