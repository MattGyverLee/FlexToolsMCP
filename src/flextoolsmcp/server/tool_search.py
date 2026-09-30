#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP-tool matching for flextools_search_by_capability (issue #312).

Weaker models search for "try_word method" or "ParserOperations.TryWord",
get zero API hits, and then invent a Flexicon method -- because nothing told
them that flextools_try_word is an MCP tool they can call directly. This
module scores the registered MCP tools (``tool_definitions.TOOLS``) against a
free-text query so the search response can point at the right tool.

Scoring (all tokens lowercased, camelCase split, plural-folded, stopwords
dropped):

- compact name hit ("tryword", "try_word", "TryWord", "ParserOperations.TryWord"
  all compact to a run that equals ``tryword``): +10
- each query token that is a tool-name token: +3 (+1 for generic verbs such as
  list/get/find/run); all name tokens covered: +4 bonus
- each query token in the description's first line: +1
- curated keyword map for the parse family and grammar_health (parse,
  unparsed, wordforms, hermitcrab, trace, sandbox, filing, slow, ...)

A tool is returned only when it reaches ``_MIN_SCORE``.
"""

import re
from typing import Any, Dict, List

# Tools never surfaced: the search tool itself (the caller is already in it)
# and the deprecated list_skeletons alias.
_EXCLUDED_TOOLS = frozenset({
    "flextools_search_by_capability",
    "flextools_list_skeletons",
})

MCP_TOOL_NOTE = (
    "This is an MCP tool -- call it directly; it is not a Flexicon/LibLCM "
    "method and cannot be imported in run_module code."
)

_MIN_SCORE = 4

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
    "from", "by", "at", "as", "is", "are", "be", "it", "its", "this", "that",
    "these", "those", "my", "me", "i", "we", "you", "your", "do", "does",
    "how", "what", "which", "why", "when", "where", "can", "could", "should",
    "would", "will", "want", "need", "call", "use", "using", "via", "all",
    "any", "some", "top", "most", "get", "method", "function", "operation",
    "api", "class", "flextool", "flexicon", "liblcm", "lcm", "flexlib",
    "python", "code", "script", "one", "not", "if", "no", "into", "then",
})

# Name tokens that are too generic to carry a match on their own.
_GENERIC_NAME_TOKENS = frozenset({
    "list", "get", "find", "run", "start", "manage", "resolve", "prepare",
    "by", "in", "for",
})

# Curated keyword -> {tool: weight}. Keys are normalized (see _norm) at import.
_PARSE_FAMILY = {
    "flextools_try_word": 3,
    "flextools_parse_text": 3,
    "flextools_parse_sandbox": 2,
    "flextools_parse_status": 1,
    "flextools_parse_log": 1,
    "flextools_parse_diff": 1,
}
_RAW_KEYWORDS: Dict[str, Dict[str, int]] = {
    "parse": _PARSE_FAMILY,
    "parser": _PARSE_FAMILY,
    "parsing": _PARSE_FAMILY,
    "parsed": _PARSE_FAMILY,
    "hermitcrab": _PARSE_FAMILY,
    "hc": _PARSE_FAMILY,
    "unparsed": {"flextools_parse_text": 4, "flextools_try_word": 3},
    "coverage": {"flextools_parse_text": 3, "flextools_try_word": 1},
    "wordform": {"flextools_parse_text": 1, "flextools_try_word": 1},
    "trace": {"flextools_try_word": 3, "flextools_parse_log": 2},
    "sandbox": {"flextools_parse_sandbox": 4},
    "speculative": {"flextools_parse_sandbox": 3},
    "analyses": {"flextools_parse_text": 3},
    "analysis": {"flextools_parse_text": 2},
    "filing": {"flextools_parse_text": 3},
    "guesses": {"flextools_parse_text": 2},
    "corpus": {"flextools_parse_text": 3},
    "batch": {"flextools_parse_text": 2, "flextools_parse_diff": 1},
    "regression": {"flextools_parse_diff": 3},
    "compare": {"flextools_parse_diff": 2},
    "lock": {"flextools_parse_release": 3},
    "grammar": {"flextools_grammar_health": 3, "flextools_parse_sandbox": 1},
    "slow": {"flextools_grammar_health": 4},
    "explosion": {"flextools_grammar_health": 4},
    "combinatorial": {"flextools_grammar_health": 4},
    "timeout": {"flextools_grammar_health": 3},
    "recipe": {"flextools_list_recipes": 3},
}


def _norm(token: str) -> str:
    """Fold a simple plural so 'wordforms'/'wordform' and 'texts'/'text' meet."""
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _raw_tokens(text: str) -> List[str]:
    """Split camelCase, then on anything non-alphanumeric; lowercase."""
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text or "")
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    return [t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if t]


def _tokens(text: str) -> List[str]:
    """Content tokens: normalized, no stopwords, no pure numbers."""
    out = []
    for t in _raw_tokens(text):
        t = _norm(t)
        if t in _STOPWORDS or t.isdigit():
            continue
        out.append(t)
    return out


_KEYWORDS: Dict[str, Dict[str, int]] = {_norm(k): v for k, v in _RAW_KEYWORDS.items()}


def _compact_candidates(query: str) -> set:
    """Every run of 1-3 adjacent raw tokens, concatenated ("try"+"word")."""
    raw = _raw_tokens(query)
    out = set()
    for i in range(len(raw)):
        for j in range(i + 1, min(i + 3, len(raw)) + 1):
            out.add("".join(raw[i:j]))
    return out


def _summary(description: str) -> str:
    for line in (description or "").strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _name_tokens(name: str) -> List[str]:
    return [_norm(t) for t in name.split("_") if t and t != "flextools"]


def _tools() -> Dict[str, Any]:
    try:
        from .tool_definitions import TOOLS
    except ImportError:
        from server.tool_definitions import TOOLS
    return TOOLS


def _visible(name: str, tool: Any) -> bool:
    if name in _EXCLUDED_TOOLS:
        return False
    return not _summary(getattr(tool, "description", "")).upper().startswith("DEPRECATED")


def score_tool(query: str, name: str, description: str) -> int:
    """Score one tool against a query (0 = no signal)."""
    q_tokens = set(_tokens(query))
    name_toks = _name_tokens(name)
    compact = "".join(t for t in name.split("_") if t != "flextools")
    score = 0

    if compact in _compact_candidates(query):
        score += 10

    matched_name = [t for t in name_toks if t in q_tokens]
    for t in matched_name:
        score += 1 if t in _GENERIC_NAME_TOKENS else 3
    if name_toks and len(matched_name) == len(name_toks) and len(name_toks) > 1:
        score += 4

    summary_toks = set(_tokens(_summary(description))) - set(name_toks)
    score += len(q_tokens & summary_toks)

    for t in q_tokens:
        score += _KEYWORDS.get(t, {}).get(name, 0)
    return score


def find_mcp_tools(query: str, max_results: int = 3) -> List[Dict[str, str]]:
    """Return up to ``max_results`` MCP tools matching ``query``, best first."""
    if not query or not query.strip():
        return []
    scored = []
    for name, tool in _tools().items():
        if not _visible(name, tool):
            continue
        s = score_tool(query, name, getattr(tool, "description", ""))
        if s >= _MIN_SCORE:
            scored.append((s, name, tool))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [
        {
            "tool": name,
            "summary": _summary(getattr(tool, "description", "")),
            "note": MCP_TOOL_NOTE,
        }
        for _s, name, tool in scored[:max_results]
    ]


def list_mcp_tools() -> List[Dict[str, str]]:
    """Compact catalog of every non-deprecated MCP tool (name + summary line)."""
    return [
        {"tool": name, "summary": _summary(getattr(tool, "description", ""))}
        for name, tool in _tools().items()
        if _visible(name, tool)
    ]


def build_zero_result_fallback() -> Dict[str, Any]:
    """Guidance block for a search that found no API members."""
    message = (
        "No Flexicon/LibLCM members matched. The capability may be an MCP tool "
        "(call it directly -- e.g. flextools_try_word to check why a word does "
        "not parse, flextools_parse_text to parse a corpus) or a shipped recipe. "
        "Do not invent method names; refine the query or use a tool below."
    )
    return {
        "message": message,
        "mcp_tools": list_mcp_tools(),
        "recipes_hint": "call flextools_list_recipes to browse shipped + local recipes",
    }
