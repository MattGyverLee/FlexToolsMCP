"""Exclusive-only operations: what must not run while FieldWorks holds a project.

Shared mode lets the MCP write while FLEx has the project open
(docs/SHARED-MODE.md). Two kinds of change are still unsafe from a peer
(spec `specs/exclusive-access-gate/spec.md` FR-001/FR-002, research R3):

* Writing-system changes crash the FLEx that holds the project
  (`crashes_holder`, seen live in the shared-mode CP4 session).
* Custom-field definitions written by a peer are never persisted: the commit
  log carries only object adds/updates/deletes, and the master writes only its
  own custom-field list (`silently_lost`, from LCM source).

`EXCLUSIVE_ONLY_OPERATIONS` is the single source for the detector below, the
`requires_exclusive_access` refusal and the "Close FLEx for these" table in
docs/SHARED-MODE.md (a test keeps the doc in step with the categories).

`detect_exclusive_only_operations` has two layers (research R2):

1. Wrapper calls. It filters the rows `certify_script_readonly` already
   resolved (facade, alias, accessor and fail-closed receivers), so detection
   is never weaker than mutation detection. Guards are ignored on purpose: a
   guarded call still runs on a write-enabled run.
2. Raw LCM calls. One AST walk matches the names that exist only on these LCM
   interfaces, generic method names (`Set`, `Add`, `Save`, ...) only on the
   writing-system manager and lists, and assignments to the schema properties.

Value edits (`CustomFieldOperations.SetValue` and friends) are ordinary data
writes and are deliberately absent from the table.
"""

from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

_WS_LIVE_EVIDENCE = "specs/_archive/shared-mode-access/evidence/live-cp4.md Item 5"
_CF_SOURCE_EVIDENCE = (
    "seen live 2026-10-02: specs/exclusive-access-gate/evidence/live-gate.md V7; "
    "liblcm SharedXMLBackendProvider.cs:429,479; CommitLogRecord.cs:23-48"
)


@dataclass(frozen=True)
class ExclusiveOnlyOperation:
    """One row of the table (data-model.md)."""

    key: str
    category: str  # "writing_system" | "custom_field"
    failure_class: str  # "crashes_holder" | "silently_lost"
    wrapper: Optional[Tuple[str, FrozenSet[str]]] = None
    raw_names: FrozenSet[str] = frozenset()
    raw_receiver_methods: Optional[Tuple[FrozenSet[str], FrozenSet[str]]] = None
    raw_assignments: FrozenSet[str] = frozenset()
    reason: str = ""
    evidence: str = ""
    # True for an idempotent call that writes only when the project lacks what
    # it asks for (WritingSystems.Ensure). Such a call is decided from a fresh
    # read of the project instead of refused outright, and flexicon's peer
    # schema guard backs the decision up at run time (plan_conditional).
    conditional: bool = False


@dataclass(frozen=True)
class ExclusiveOnlyMatch:
    """One exclusive-only call found in a script (data-model.md)."""

    key: str
    category: str
    failure_class: str
    call: str
    line: Optional[int]
    source: str  # "wrapper" | "raw"
    conditional: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


_WS_REASON = (
    "Writing-system changes made while FieldWorks has the project open crash "
    "that FieldWorks session."
)
_CF_REASON = (
    "Custom-field definitions written while FieldWorks has the project open "
    "are never saved, so the field silently disappears."
)

EXCLUSIVE_ONLY_OPERATIONS: Tuple[ExclusiveOnlyOperation, ...] = (
    ExclusiveOnlyOperation(
        key="ws.wrapper",
        category="writing_system",
        failure_class="crashes_holder",
        wrapper=(
            "WritingSystemOperations",
            frozenset({
                "Create", "Delete", "SetFontName", "SetFontSize",
                "SetRightToLeft", "SetDefaultVernacular", "SetDefaultAnalysis",
            }),
        ),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE,
    ),
    ExclusiveOnlyOperation(
        key="ws.ensure",
        category="writing_system",
        failure_class="crashes_holder",
        # Ensure() writes only when the tag is not already active in the
        # requested category; an already-active tag is a no-op.
        wrapper=("WritingSystemOperations", frozenset({"Ensure"})),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; flexicon WritingSystemOperations.Ensure no-op path",
        conditional=True,
    ),
    ExclusiveOnlyOperation(
        key="cf.wrapper",
        category="custom_field",
        failure_class="silently_lost",
        wrapper=(
            "CustomFieldOperations",
            frozenset({"CreateField", "DeleteField", "SetFieldName"}),
        ),
        reason=_CF_REASON,
        evidence=_CF_SOURCE_EVIDENCE,
    ),
    ExclusiveOnlyOperation(
        key="cf.raw",
        category="custom_field",
        failure_class="silently_lost",
        # UpdateCustomField also covers FLEx's own FieldDescription route.
        raw_names=frozenset({"AddCustomField", "UpdateCustomField", "DeleteCustomField"}),
        raw_assignments=frozenset({"MarkForDeletion"}),
        reason=_CF_REASON,
        evidence=_CF_SOURCE_EVIDENCE + "; LcmMetaDataCache.cs:920,1016,1068,1093; FieldDescription.cs:336",
    ),
    ExclusiveOnlyOperation(
        key="ws.raw.manager",
        category="writing_system",
        failure_class="crashes_holder",
        raw_receiver_methods=(
            frozenset({"WritingSystemManager"}),
            frozenset({"Set", "GetOrSet", "Replace", "Save"}),
        ),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; liblcm WritingSystemManager.cs:271,287,331,346,412",
    ),
    ExclusiveOnlyOperation(
        key="ws.raw.container",
        category="writing_system",
        failure_class="crashes_holder",
        raw_names=frozenset({
            "AddToCurrentVernacularWritingSystems",
            "AddToCurrentAnalysisWritingSystems",
        }),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; liblcm IWritingSystemContainer",
    ),
    ExclusiveOnlyOperation(
        key="ws.raw.lists",
        category="writing_system",
        failure_class="crashes_holder",
        raw_receiver_methods=(
            frozenset({
                "VernacularWritingSystems", "AnalysisWritingSystems",
                "CurrentVernacularWritingSystems", "CurrentAnalysisWritingSystems",
            }),
            frozenset({"Add", "Remove", "Insert", "Clear"}),
        ),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; liblcm LangProject writing-system lists",
    ),
    ExclusiveOnlyOperation(
        key="ws.raw.services",
        category="writing_system",
        failure_class="crashes_holder",
        raw_receiver_methods=(
            frozenset({"WritingSystemServices"}),
            frozenset({
                "FindOrCreateWritingSystem", "FindOrCreateSomeWritingSystem",
                "UpdateWritingSystemFields", "DeleteWritingSystem",
                "MergeWritingSystems", "UpdateWritingSystemId",
            }),
        ),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; liblcm WritingSystemServices.cs:1327-1665",
    ),
    ExclusiveOnlyOperation(
        key="ws.raw.props",
        category="writing_system",
        failure_class="crashes_holder",
        raw_assignments=frozenset({
            "DefaultVernacularWritingSystem", "DefaultAnalysisWritingSystem",
            "DefaultFontName", "DefaultFont", "DefaultFontSize", "RightToLeftScript",
        }),
        reason=_WS_REASON,
        evidence=_WS_LIVE_EVIDENCE + "; flexicon WritingSystemOperations setters",
    ),
)

#: The row label each category has in docs/SHARED-MODE.md "Close FLEx for
#: these" (tests/test_docs_no_undo_claims.py keeps the two in step).
CATEGORY_LABELS: Dict[str, str] = {
    "custom_field": "Custom field",
    "writing_system": "Writing system",
}

ROWS_BY_KEY: Dict[str, ExclusiveOnlyOperation] = {
    row.key: row for row in EXCLUSIVE_ONLY_OPERATIONS
}

# Wrapper method names that are NOT matched by name alone on an untyped
# receiver (the certifier's `unresolved_receiver` rows). `Create` and `Delete`
# are mutating on ~50 other Operations classes in the 4.11 index and on every
# raw LCM factory, so an untyped `x.Create()` is almost always an ordinary
# entry/sense write. Refusing it would tell users to close FLEx for an
# ordinary edit (US2). Every other wrapper name is unique to these classes
# (or nearly so) and still matches by name.
_GENERIC_WRAPPER_NAMES = frozenset({"Create", "Delete"})

_CERT_BUCKETS = ("mutating_calls", "protected_calls", "unknown_calls")


def _is_unresolved_row(row: dict) -> bool:
    if row.get("source") == "unresolved_receiver":
        return True
    return str(row.get("reason", "")).startswith("receiver could not be typed")


def _match(op: ExclusiveOnlyOperation, call: str, line: Optional[int], source: str) -> ExclusiveOnlyMatch:
    return ExclusiveOnlyMatch(
        key=op.key,
        category=op.category,
        failure_class=op.failure_class,
        call=call,
        line=line,
        source=source,
        conditional=op.conditional,
    )


def _wrapper_matches(cert: dict) -> List[ExclusiveOnlyMatch]:
    # (class, method) -> row; one class can own several rows (ws.wrapper and
    # the conditional ws.ensure).
    by_class_method: Dict[Tuple[str, str], ExclusiveOnlyOperation] = {}
    wrapper_classes: Set[str] = set()
    by_name: Dict[str, ExclusiveOnlyOperation] = {}
    for op in EXCLUSIVE_ONLY_OPERATIONS:
        if op.wrapper is None:
            continue
        wrapper_classes.add(op.wrapper[0])
        for method in op.wrapper[1]:
            by_class_method[(op.wrapper[0], method)] = op
        for method in op.wrapper[1] - _GENERIC_WRAPPER_NAMES:
            by_name[method] = op

    out: List[ExclusiveOnlyMatch] = []
    for bucket in _CERT_BUCKETS:
        for row in cert.get(bucket) or []:
            cls, method = row.get("class"), row.get("method")
            if not cls or not method:
                continue
            if cls in wrapper_classes:
                op = by_class_method.get((cls, method))
            elif _is_unresolved_row(row):
                op = by_name.get(method)
            else:
                op = None
            if op is not None:
                out.append(_match(op, f"{cls}.{method}", row.get("line"), "wrapper"))
    return out


def _chain_names(node: ast.AST) -> List[str]:
    """Identifiers along a receiver chain: `a.b(x).c[0].d` -> [a, b, c, d]."""
    names: List[str] = []
    current = node
    while True:
        if isinstance(current, ast.Attribute):
            names.append(current.attr)
            current = current.value
        elif isinstance(current, ast.Call):
            current = current.func
        elif isinstance(current, ast.Subscript):
            current = current.value
        elif isinstance(current, ast.Name):
            names.append(current.id)
            break
        else:
            break
    return names


_SCOPE_TYPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _scope_nodes(scope: ast.AST) -> Iterable[ast.AST]:
    """Every node in `scope` without descending into nested scopes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, _SCOPE_TYPES):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _receiver_aliases(scope: ast.AST, receivers: Set[str], inherited: Dict[str, str]) -> Dict[str, str]:
    """Local names bound (directly or through a rebind) to a raw receiver.

    `mgr = cache.ServiceLocator.WritingSystemManager` -> {"mgr": "WritingSystemManager"}.
    """
    aliases = dict(inherited)
    pending: List[Tuple[str, ast.AST]] = []
    for node in _scope_nodes(scope):
        if isinstance(node, ast.Assign):
            value = node.value
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
            value = node.value
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                pending.append((target.id, value))
    changed = True
    while changed:
        changed = False
        for name, value in pending:
            if name in aliases:
                continue
            chain = _chain_names(value)
            hit = next((n for n in chain if n in receivers), None)
            if hit is None and isinstance(value, ast.Name) and value.id in aliases:
                hit = aliases[value.id]
            if hit is not None:
                aliases[name] = hit
                changed = True
    return aliases


def _raw_matches(tree: ast.AST) -> List[ExclusiveOnlyMatch]:
    by_name: Dict[str, ExclusiveOnlyOperation] = {}
    by_assignment: Dict[str, ExclusiveOnlyOperation] = {}
    receiver_rows: List[ExclusiveOnlyOperation] = []
    for op in EXCLUSIVE_ONLY_OPERATIONS:
        for name in op.raw_names:
            by_name[name] = op
        for name in op.raw_assignments:
            by_assignment[name] = op
        if op.raw_receiver_methods is not None:
            receiver_rows.append(op)
    all_receivers: Set[str] = set()
    for op in receiver_rows:
        all_receivers |= op.raw_receiver_methods[0]

    def match(op: ExclusiveOnlyOperation, node: ast.AST, call: str) -> ExclusiveOnlyMatch:
        return _match(op, call, getattr(node, "lineno", None), "raw")

    out: List[ExclusiveOnlyMatch] = []
    module_aliases = _receiver_aliases(tree, all_receivers, {})
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, _SCOPE_TYPES[1:])]
    for scope in scopes:
        aliases = (
            module_aliases if scope is tree
            else _receiver_aliases(scope, all_receivers, module_aliases)
        )
        for node in _scope_nodes(scope):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                call = ast.unparse(node.func)
                op = by_name.get(attr)
                if op is not None:
                    out.append(match(op, node, call))
                    continue
                chain = _chain_names(node.func.value)
                chain_receivers = {n for n in chain if n in all_receivers}
                if isinstance(node.func.value, ast.Name) and node.func.value.id in aliases:
                    chain_receivers.add(aliases[node.func.value.id])
                if not chain_receivers:
                    continue
                for op in receiver_rows:
                    recv, methods = op.raw_receiver_methods
                    if attr in methods and chain_receivers & recv:
                        out.append(match(op, node, call))
                        break
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                flat: List[ast.AST] = []
                for target in targets:
                    if isinstance(target, (ast.Tuple, ast.List)):
                        flat.extend(target.elts)
                    else:
                        flat.append(target)
                for target in flat:
                    if isinstance(target, ast.Attribute) and target.attr in by_assignment:
                        out.append(match(
                            by_assignment[target.attr], node, ast.unparse(target) + " = ..."
                        ))
    return out


#: Probe verdicts on which an exclusive-only script is refused (FR-004, FR-006).
#: `open_exclusive` / `held_by_other` keep their own `project_locked` refusal
#: (FR-007); `free` / `stale_lock` mean FieldWorks does not hold the project.
GATED_VERDICTS = ("open_shared", "unknown")

REFUSAL_GUIDANCE = (
    "1. Close FieldWorks (all windows for this project). "
    "2. Re-submit this exact run_module call unchanged. "
    "3. Reopen FieldWorks after it finishes."
)


def build_refusal(
    project_name: str,
    verdict: str,
    matches: List[ExclusiveOnlyMatch],
    holder_pid: Optional[int] = None,
    holder_process: Optional[str] = None,
    notes: Optional[List[str]] = None,
    stage: str = "preflight",
) -> Tuple[str, dict]:
    """Message and detail fields for a `requires_exclusive_access` refusal.

    The detail fields are spread into `error_response()` (the envelope adds
    `error_code`), in RequiresExclusiveAccessDetail order. The message names
    each matched operation and gives the reason per category (FR-008).
    `notes` (from plan_conditional) say why a conditional call was refused.
    """
    if verdict == "unknown":
        opening = (
            "This script changes writing systems or custom fields, and the server "
            f"could not confirm that FieldWorks has '{project_name}' closed."
        )
        remedy = (
            "FieldWorks could not be confirmed closed (the project's lock state "
            "could not be read). Make sure FieldWorks is closed, re-submit "
            "unchanged, reopen FieldWorks."
        )
    else:
        opening = (
            "This script changes writing systems or custom fields, which is not "
            f"safe while FieldWorks has '{project_name}' open."
        )
        remedy = "Close FieldWorks, re-submit unchanged, reopen FieldWorks."

    calls = ", ".join(
        f"{m.call} (line {m.line})" if m.line is not None else m.call for m in matches
    )
    reasons: List[str] = []
    for m in matches:
        reason = ROWS_BY_KEY[m.key].reason
        if reason not in reasons:
            reasons.append(reason)
    message = (
        f"{opening} Close FieldWorks, re-submit this same call, then reopen "
        f"FieldWorks. Operations: {calls}. " + " ".join(reasons + list(notes or []))
    )
    detail = {
        "guidance": REFUSAL_GUIDANCE,
        "verdict": verdict,
        "holder_pid": holder_pid,
        "holder_process": holder_process,
        "operations": [m.to_dict() for m in matches],
        "remedy": remedy,
        "stage": stage,
    }
    return message, detail


def detect_exclusive_only_operations(
    code: str, tree: Optional[ast.AST], cert: dict
) -> List[ExclusiveOnlyMatch]:
    """Find exclusive-only operations in `code`.

    `tree` is the handler's already-parsed AST (parsed here when None; a
    syntax error leaves only the certifier rows). `cert` is the result of
    `certify_script_readonly` for the same code. Returns matches
    de-duplicated on `(key, line)` and sorted by line.
    """
    if tree is None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            tree = None

    found = _wrapper_matches(cert or {})
    if tree is not None:
        found.extend(_raw_matches(tree))

    seen: Set[Tuple[str, Optional[int]]] = set()
    unique: List[ExclusiveOnlyMatch] = []
    for m in found:
        if (m.key, m.line) in seen:
            continue
        seen.add((m.key, m.line))
        unique.append(m)
    unique.sort(key=lambda m: (m.line is None, m.line or 0, m.key))
    return unique


# ---------------------------------------------------------------------------
# Conditional calls (WritingSystems.Ensure)
#
# Ensure() writes only when the tag is not already active in the requested
# category. Two layers decide whether one may run while FieldWorks holds the
# project:
#   1. Before the run, the project's ACTIVE writing-system lists are read
#      straight from the .fwdata (read_active_writing_systems: the
#      CurVernWss / CurAnalysisWss elements, the same lists flexicon's
#      Ensure() tests against). Pure filesystem, like the access probe; it
#      never opens the project. Literal calls are settled here: already active
#      -> let it through; would add -> refuse now, before confirmation, backup
#      or run. The .ldml store is NOT enough: a store-present tag can be
#      inactive, and Ensure() would then activate it (a write).
#   2. During the run, flexicon's peer schema guard (capability
#      "peer-schema-guard") refuses any Ensure() that turns out to need a write,
#      before it writes. That covers a stale file (FLEx holds unsaved changes,
#      or the user changed writing systems in between), arguments that are not
#      literals, and a file that could not be read.
# Without the guard, layer 1 alone is not safe (a stale read errs in the
# direction that crashes FLEx), so conditional calls are refused as before.
# ---------------------------------------------------------------------------

#: flexicon capability token for the runtime guard.
PEER_SCHEMA_GUARD_CAPABILITY = "peer-schema-guard"

#: Runner modes for the guard (PEER_SCHEMA_GUARD in the generated runner).
#:   "off"      -- do not touch the guard
#:   "on"       -- enable it if flexicon offers it (backstop for every
#:                 write-enabled run while FieldWorks holds the project)
#:   "required" -- a conditional call was let through on the guard's strength;
#:                 refuse the run before any user code if it cannot be enabled
GUARD_OFF, GUARD_ON, GUARD_REQUIRED = "off", "on", "required"


def _norm_tag(tag: str) -> str:
    """Tag comparison as flexicon's Exists() does it: case- and '_'/'-'-blind."""
    return tag.strip().lower().replace("_", "-")


def _literal(node: Optional[ast.AST]):
    if isinstance(node, ast.Constant):
        return node.value
    return _NOT_LITERAL


_NOT_LITERAL = object()


def ensure_call_args(tree: Optional[ast.AST]) -> Dict[int, List[Optional[Tuple[str, bool]]]]:
    """Literal `(language_tag, is_vernacular)` of every `.Ensure(...)` call, by line.

    A call whose tag or `is_vernacular` is not a literal maps to None (decided
    at run time). `is_vernacular` defaults to True, as in flexicon.
    """
    out: Dict[int, List[Optional[Tuple[str, bool]]]] = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Ensure"):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        tag_node = node.args[0] if node.args else kwargs.get("language_tag")
        if len(node.args) >= 3:
            vern_node = node.args[2]
        else:
            vern_node = kwargs.get("is_vernacular")
        tag = _literal(tag_node)
        vern = True if vern_node is None else _literal(vern_node)
        resolved: Optional[Tuple[str, bool]] = None
        if isinstance(tag, str) and tag.strip() and isinstance(vern, bool):
            resolved = (tag, vern)
        out.setdefault(node.lineno, []).append(resolved)
    return out


@dataclass(frozen=True)
class ConditionalPlan:
    """What plan_conditional decided for one run."""

    refuse: Tuple[ExclusiveOnlyMatch, ...]  # refuse the run with these
    notes: Tuple[str, ...]                  # why (for the refusal message)
    satisfied: Tuple[ExclusiveOnlyMatch, ...] = ()  # settled no-op by the file read
    deferred: Tuple[ExclusiveOnlyMatch, ...] = ()   # left to the runtime guard

    @property
    def allowed(self) -> bool:
        return not self.refuse


_ACTIVE_WS_ELEMENTS = {"CurVernWss": "vernacular", "CurAnalysisWss": "analysis"}
_WS_OPEN_RE = re.compile(r"<(CurVernWss|CurAnalysisWss)>")
_UNI_RE = re.compile(r"<Uni>([^<]*)</Uni>|<Uni\s*/>")


def read_active_writing_systems(fwdata_path) -> Optional[Dict[str, List[str]]]:
    """Active vernacular / analysis tags from a project's .fwdata, or None.

    Streams the file for the LangProject `CurVernWss` / `CurAnalysisWss`
    elements (space-separated tags in a `<Uni>` child) and stops as soon as
    both are found. Never opens the project, so it is safe while FieldWorks
    holds it. Returns None when the file cannot be read or either element is
    missing; plan_conditional then leaves the call to the runtime guard.

    The file can lag what FieldWorks holds unsaved. That is acceptable only
    because the runtime guard backs this read up (see the section comment).
    """
    found: Dict[str, List[str]] = {}
    pending: Optional[str] = None
    try:
        with open(fwdata_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if pending is None:
                    opened = _WS_OPEN_RE.search(line)
                    if opened is None:
                        continue
                    pending = _ACTIVE_WS_ELEMENTS[opened.group(1)]
                    line = line[opened.end():]
                uni = _UNI_RE.search(line)
                if uni is not None:
                    found[pending] = (uni.group(1) or "").split()
                    pending = None
                    if len(found) == len(_ACTIVE_WS_ELEMENTS):
                        return found
    except OSError:
        return None
    return None


def plan_conditional(
    matches: List[ExclusiveOnlyMatch],
    ensure_args: Dict[int, List[Optional[Tuple[str, bool]]]],
    active: Optional[Dict[str, List[str]]],
    guard_available: bool,
) -> ConditionalPlan:
    """Decide a gated run whose exclusive-only matches may be conditional.

    `active` is read_active_writing_systems() output, or None when the read
    failed. `guard_available` says whether the run's flexicon offers the peer
    schema guard (the runner refuses to start if that turns out wrong).

    - Any unconditional match refuses everything.
    - No guard refuses everything: without it a stale read could let a
      writing Ensure() through.
    - With the guard: a literal tag active in its category is satisfied; a
      literal tag that would be added refuses now; a non-literal call, or any
      call when the file could not be read, is deferred to the guard.
    """
    matches = list(matches)
    hard = [m for m in matches if not m.conditional]
    if hard:
        return ConditionalPlan(refuse=tuple(matches), notes=())
    if not guard_available:
        return ConditionalPlan(refuse=tuple(matches), notes=(
            "The installed flexicon has no peer schema guard "
            f"('{PEER_SCHEMA_GUARD_CAPABILITY}'), so a no-op Ensure() cannot be "
            "told apart safely from one that writes.",
        ))
    if active is None:
        return ConditionalPlan(refuse=(), notes=(), deferred=tuple(matches))

    active_by_vern = {
        True: {_norm_tag(t) for t in active.get("vernacular") or []},
        False: {_norm_tag(t) for t in active.get("analysis") or []},
    }
    refuse: List[ExclusiveOnlyMatch] = []
    notes: List[str] = []
    satisfied: List[ExclusiveOnlyMatch] = []
    deferred: List[ExclusiveOnlyMatch] = []
    for m in matches:
        calls = ensure_args.get(m.line) if m.line is not None else None
        if not calls or any(c is None for c in calls):
            deferred.append(m)
            continue
        missing = [(tag, vern) for tag, vern in calls if _norm_tag(tag) not in active_by_vern[vern]]
        if missing:
            refuse.append(m)
            for tag, vern in missing:
                notes.append(
                    f"Ensure({tag!r}) on line {m.line} would add "
                    f"{'a vernacular' if vern else 'an analysis'} writing system: "
                    f"'{tag}' is not active as "
                    f"{'vernacular' if vern else 'analysis'} in the project."
                )
        else:
            satisfied.append(m)
    return ConditionalPlan(
        refuse=tuple(refuse), notes=tuple(notes),
        satisfied=tuple(satisfied), deferred=tuple(deferred),
    )


def conditional_after_writes(matches: List[ExclusiveOnlyMatch], cert: dict) -> List[ExclusiveOnlyMatch]:
    """Conditional calls that come after some other write in the script.

    If such a call is refused at run time, the earlier writes have already
    committed (each wrapper call saves its own change), so the run stops part
    way. Used for a warning, not a refusal.
    """
    write_lines = sorted(
        r.get("line") for bucket in ("mutating_calls", "protected_calls")
        for r in (cert or {}).get(bucket) or []
        if r.get("line") is not None and r.get("method") != "Ensure"
    )
    if not write_lines:
        return []
    first_write = write_lines[0]
    return [m for m in matches if m.conditional and m.line is not None and m.line > first_write]
