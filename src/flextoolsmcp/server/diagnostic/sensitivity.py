#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`likely_contains_lexical_data` code-shape sensitivity flag (spec section 9,
resolved Q4) -- CP3.

Detected from the SHAPE of the op's code via `ast`, never from the string
VALUES it produces at runtime (report.Info output, glosses, headwords,
etc.) -- detection itself must neither inspect nor leak lexical data.

Fires when EITHER:
  (a) the code calls a known lexical accessor (`GetGloss`, `GetDefinition`,
      `GetLexemeForm`, `.BestVernacularAlternative`, `.BestAnalysisAlternative`,
      `.Text` on a multistring) and that result flows -- directly, via a
      simple local variable, or through string formatting -- into a
      `report.Info(...)` call; or
  (b) the code references a BCP-47-shaped writing-system tag (a STRING
      LITERAL matching the narrow `xx` / `xx-YY` BCP-47 shape -- checked by
      regex against the literal's SHAPE, not by reading lexical content)
      alongside a multistring accessor anywhere in the same code.

This flag ONLY selects which sentence Claude uses to frame the email-vs-
GitHub choice (spec section 9); it is NEVER the send decision (GitHub stays
default, "don't send" always available) and NEVER alters the local report
file, which is always full-fidelity regardless (spec section 7.1).

Pure functions only -- no I/O, no network. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard
this module lives under.
"""

import ast
import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from .reconstruct import ReportSlice

try:
    from .render import _extract_code_block
except ImportError:
    from server.diagnostic.render import _extract_code_block

# Lexical accessor CALL names (spec section 9): `project.LexSense.GetGloss(sense)`-shaped.
_LEXICAL_ACCESSOR_CALL_NAMES = frozenset({"GetGloss", "GetDefinition", "GetLexemeForm"})

# Lexical accessor ATTRIBUTE names (spec section 9): `.BestVernacularAlternative`,
# `.BestAnalysisAlternative`, `.Text` on a multistring field.
_LEXICAL_ACCESSOR_ATTR_NAMES = frozenset(
    {"BestVernacularAlternative", "BestAnalysisAlternative", "Text"}
)

# BCP-47-shaped writing-system tag: narrow on purpose (2-3 letter primary
# subtag, 1-3 hyphenated subtags of 2-8 alnum chars) so it matches tags like
# "en", "fr-FR", "es-419" and essentially never matches ordinary prose or a
# gloss/headword string -- this is a SHAPE check, not a content check.
_BCP47_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")


class _LexicalFlowVisitor(ast.NodeVisitor):
    """Walks one op's code AST tracking whether a lexical accessor's result
    flows into a `report.Info(...)` call, and whether a lexical accessor is
    referenced anywhere alongside a BCP-47-shaped string literal."""

    def __init__(self) -> None:
        self.lexical_vars: set = set()
        self.found_flow: bool = False
        self.found_lexical_accessor: bool = False
        self.found_ws_tag: bool = False

    # -- helpers -----------------------------------------------------
    def _is_lexical_accessor_call(self, node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _LEXICAL_ACCESSOR_CALL_NAMES:
            return True
        if isinstance(func, ast.Name) and func.id in _LEXICAL_ACCESSOR_CALL_NAMES:
            return True
        return False

    def _expr_has_lexical_accessor(self, node: ast.AST) -> bool:
        for n in ast.walk(node):
            if isinstance(n, ast.Attribute) and n.attr in _LEXICAL_ACCESSOR_ATTR_NAMES:
                return True
            if self._is_lexical_accessor_call(n):
                return True
        return False

    def _expr_has_lexical_var(self, node: ast.AST) -> bool:
        for n in ast.walk(node):
            if isinstance(n, ast.Name) and n.id in self.lexical_vars:
                return True
        return False

    # -- visitors ------------------------------------------------------
    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _LEXICAL_ACCESSOR_ATTR_NAMES:
            self.found_lexical_accessor = True
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str) and _BCP47_RE.match(node.value):
            self.found_ws_tag = True
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._expr_has_lexical_accessor(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.lexical_vars.add(target.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_lexical_accessor_call(node):
            self.found_lexical_accessor = True

        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "Info":
            for arg_expr in list(node.args) + [kw.value for kw in node.keywords]:
                if self._expr_has_lexical_accessor(arg_expr) or self._expr_has_lexical_var(arg_expr):
                    self.found_flow = True
        self.generic_visit(node)


def detect_lexical_shape(code: str) -> bool:
    """Return True if `code`'s AST shape matches either sensitivity
    condition (a) or (b) above. Returns False (never raises) on code that
    fails to parse -- a partial/invalid snippet is not evidence of anything.
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return False

    visitor = _LexicalFlowVisitor()
    visitor.visit(tree)

    if visitor.found_flow:
        return True
    if visitor.found_ws_tag and visitor.found_lexical_accessor:
        return True
    return False


def likely_contains_lexical_data(slice_obj: "ReportSlice") -> bool:
    """Inspect the CODE TEXT of every op in a reconstructed `ReportSlice`
    (never the report.Info/report.Error runtime OUTPUT, which may itself
    contain lexical data -- only the submitted code's shape) for the
    section-9 sensitivity signal.

    The code text lives in each `SliceOp.log_lines` (the `Code:` block
    already extracted by `render._extract_code_block()`); this function
    reuses that extractor rather than re-deriving it, so both modules agree
    on where the "code" boundary is.
    """
    for op in slice_obj.ops:
        code_lines: List[str] = _extract_code_block(op.log_lines)
        if not code_lines:
            continue
        code_text = "\n".join(code_lines)
        if code_text.strip() and detect_lexical_shape(code_text):
            return True
    return False
