#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`worker_main._summarize_trace` -- the three-way outcome, derived (parser-check
CP2b honesty gap; specs/parser-check-cp2b/reviews/cycle1-domain.md,
cycle1-qc-pattern-audit.md).

`_summarize_trace` reads the `XDocument` `TraceWordXml`/`ParseWordXml` hand
back, BEFORE the worker's `_as_text` collapses it to a string. Root is
`<Wordform>` (HCParser.cs:207); `<Analysis>` children are added independently
of the tracing flag (HCParser.cs:213-215); a caught exception appends
`<Error>` INSTEAD of any `<Analysis>` (HCParser.cs:219-222).

These stand-ins implement the slice of `System.Xml.Linq.XElement`'s public
surface `_summarize_trace` actually calls -- `.Root`, `.Elements()` (no
argument), `.Name.LocalName`, `.Value` -- and, CRUCIALLY, reject a bare
`str` argument to `.Element()`/`.Elements()` the same way pythonnet's real
binding does in this environment (cycle 3 live verification:
`TypeError: No method matches given arguments for XContainer.Element:
(<class 'str'>)`; there is no implicit `str -> XName` conversion for that
overload here). A double that accepted a string argument silently -- as an
earlier version of this file did -- could not have caught that live defect;
2016 mock tests passed while the real call raised on every `explain`/
`restricted` request. This is a unit test of the derivation logic against
that CLR-faithful contract, NOT a live check that pythonnet's real
`XDocument` behaves identically in every environment. That live confirmation
is out of reach without a FieldWorks project and a real HC grammar; it is
not attempted here and is named as such in this checkpoint's report.

Run with:
    python -m pytest tests/test_summarize_trace.py -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.worker_main import _summarize_trace  # noqa: E402


class _FakeXName:
    """Stands in for `System.Xml.Linq.XName`: just `.LocalName`."""

    def __init__(self, local_name):
        self.LocalName = local_name


class _FakeXElement:
    """Stands in for `System.Xml.Linq.XElement`, CLR-binding-faithful.

    `.Element(str)` / `.Elements(str)` RAISE `TypeError`, matching
    pythonnet's real refusal to bind a bare `str` to the `XName` overload
    in this environment. `.Elements()` with NO argument works, returning
    every direct child -- the only method `_summarize_trace` may call.
    """

    def __init__(self, name, *, children=None, value=None):
        self.Name = _FakeXName(name)
        self._children = list(children or [])
        self._value = value

    def Element(self, name):
        raise TypeError(
            "No method matches given arguments for XContainer.Element: "
            f"({type(name)})"
        )

    def Elements(self, name=None):
        if name is not None:
            raise TypeError(
                "No method matches given arguments for XContainer.Elements: "
                f"({type(name)})"
            )
        return list(self._children)

    @property
    def Value(self):
        return self._value if self._value is not None else ""


class _FakeXDocument:
    """Stands in for `System.Xml.Linq.XDocument`: just a `.Root`."""

    def __init__(self, root):
        self.Root = root


def _wordform(children):
    return _FakeXDocument(_FakeXElement("Wordform", children=children))


# ---------------------------------------------------------------------------
# Outcome 1 -- one or more <Analysis>: parsed, count = len(<Analysis>)
# ---------------------------------------------------------------------------


def test_one_analysis_is_parsed_true_count_one():
    trace = _wordform([_FakeXElement("Analysis")])

    summary = _summarize_trace(trace)

    assert summary == {"parsed": True, "analysis_count": 1}


def test_several_analyses_count_all_of_them():
    trace = _wordform(
        [_FakeXElement("Analysis"), _FakeXElement("Analysis"), _FakeXElement("Analysis")]
    )

    summary = _summarize_trace(trace)

    assert summary == {"parsed": True, "analysis_count": 3}


def test_a_trace_sibling_alongside_analysis_does_not_inflate_the_count():
    """`<Trace>` holds explored/rejected paths; it is never promoted into
    `<Analysis>` (HCParser.cs:217-218), so it must not be counted as one.
    """
    trace = _wordform(
        [
            _FakeXElement("Analysis"),
            _FakeXElement("Trace", children=[_FakeXElement("Analysis")]),
        ]
    )

    summary = _summarize_trace(trace)

    assert summary == {"parsed": True, "analysis_count": 1}, (
        "the nested <Analysis> under <Trace> is a rejected candidate, not a "
        "survivor -- Elements() at the Wordform level must not see inside "
        "its sibling"
    )


# ---------------------------------------------------------------------------
# Outcome 2 -- zero <Analysis>, no <Error>: genuinely did not parse
# ---------------------------------------------------------------------------


def test_no_analysis_no_error_is_parsed_false_count_zero():
    trace = _wordform([_FakeXElement("Trace")])

    summary = _summarize_trace(trace)

    assert summary == {"parsed": False, "analysis_count": 0}


def test_a_bare_wordform_with_no_children_at_all_is_parsed_false():
    """The asymmetry to keep (see Outcome 4 below, for a rootless document):
    a document that HAS a root, and simply holds neither <Analysis> nor
    <Error>, answered honestly. That is a genuine `parsed: False`, not an
    indeterminate one -- unlike a document with no root at all.
    """
    trace = _wordform([])

    summary = _summarize_trace(trace)

    assert summary == {"parsed": False, "analysis_count": 0}


# ---------------------------------------------------------------------------
# Outcome 3 -- <Error> present: BLOCKING, and checked FIRST
# ---------------------------------------------------------------------------


def test_an_error_element_reports_parse_error_alone():
    trace = _wordform([_FakeXElement("Error", value="the morpher threw")])

    summary = _summarize_trace(trace)

    assert summary == {"parse_error": "the morpher threw"}
    assert "parsed" not in summary, (
        "a thrown parse must never be reported as a definite `parsed: "
        "False` -- that would assert a fact ('genuinely did not parse') "
        "the document does not establish"
    )
    assert "analysis_count" not in summary


def test_error_takes_precedence_even_alongside_an_analysis():
    """Defensive: ParseToXml's own contract is <Error> INSTEAD OF
    <Analysis> (HCParser.cs:219-222), so this document should not occur --
    but if it did, <Error> must still win, because reporting `parsed: True`
    for a run that also threw would be just as false as `parsed: False`.
    """
    trace = _wordform(
        [_FakeXElement("Analysis"), _FakeXElement("Error", value="boom")]
    )

    summary = _summarize_trace(trace)

    assert summary == {"parse_error": "boom"}


def test_an_error_element_with_no_text_still_reports_something_truthy():
    """An <Error> with empty/whitespace text must not collapse to a falsy
    `parse_error` that a caller's `if result.get("parse_error"):` would
    treat the same as "no error at all".
    """
    trace = _wordform([_FakeXElement("Error", value="")])

    summary = _summarize_trace(trace)

    assert "parse_error" in summary
    assert summary["parse_error"]


# ---------------------------------------------------------------------------
# Outcome 4 -- a document with no root at all: indeterminate, not a negative
# ---------------------------------------------------------------------------


def test_a_rootless_document_is_a_parse_error_not_a_negative():
    """A document we could not read is not a word that did not parse
    (Delta 6). Reporting `parsed: False` here would invent the very fact
    that outcome is supposed to avoid inventing -- so this must land in the
    same `parse_error`-alone bucket as a thrown parse, never in the
    `parsed`/`analysis_count` pair.
    """
    trace = _FakeXDocument(None)

    summary = _summarize_trace(trace)

    assert "parse_error" in summary
    assert summary["parse_error"]
    assert "parsed" not in summary
    assert "analysis_count" not in summary


# ---------------------------------------------------------------------------
# CLR-faithful regression: the exact live defect (cycle 3)
# ---------------------------------------------------------------------------


def test_never_passes_a_bare_string_to_element_or_elements():
    """This is the mock shape that could have caught the live defect.

    Every fake element here raises `TypeError` if `.Element(str)` or
    `.Elements(str)` is called -- exactly like pythonnet's real binding
    (cycle 3 live verification against IndonesianHC-Complete). Only the
    no-argument `.Elements()` pass, matched by `.Name.LocalName`, is
    permitted. If `_summarize_trace` regressed to calling
    `root.Element("Error")` or `root.Elements("Analysis")`, this test would
    raise the same `TypeError` the live parser did, instead of passing
    silently the way the old hand-rolled stand-in did.
    """
    trace = _wordform(
        [_FakeXElement("Analysis"), _FakeXElement("Analysis")]
    )

    summary = _summarize_trace(trace)

    assert summary == {"parsed": True, "analysis_count": 2}
