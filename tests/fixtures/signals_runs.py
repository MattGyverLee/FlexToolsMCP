#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared US5 fixtures (parser-check CP3): results.jsonl lines, stored-analysis
records, and a way to emit a batch report through the real handler.

Plain Python -- no FieldWorks, no pythonnet. Every shape here is the one the
worker writes (contracts/artifact.md section 4, plus the additive CP3 US5
fields `worker_main._structured_analysis` and `_human_analyses` record).
"""

import asyncio
import json
from typing import Any, Dict, List


def parser_analysis(tag, *, glosses=None, kinds=None, entries=None, cats=None, forms=None):
    """One parser analysis (`parse.analyses[i]`)."""
    n = len(glosses or forms or kinds or ["x"])
    return {
        "signature": [[f"form-{tag}-{i}", f"msa-{tag}-{i}", None] for i in range(n)],
        "rendered_morphs": list(forms or [f"{tag}{i}" for i in range(n)]),
        "category_labels": list(cats or ["v"] * n),
        "has_guessed_form": False,
        "entry_guids": list(entries or [f"entry-{tag}-{i}" for i in range(n)]),
        "morph_kinds": list(kinds or (["affix"] * (n - 1) + ["stem"])),
        "morph_glosses": list(glosses or [""] * n),
    }


def stored(guid, *, opinion="noopinion", bundles=2, complete=None, in_segment=False,
           parser_evaluated=False, evaluator="Ana", evaluated_at="2026-03-01",
           gloss="", signature=None, forms=None):
    """One stored analysis (`parse.human_analyses[i]`)."""
    return {
        "analysis_guid": guid,
        "opinion": opinion,
        "bundle_count": bundles,
        "complete_bundle_count": bundles if complete is None else complete,
        "signature": signature if signature is not None else
                     [[f"form-{guid}-{i}", f"msa-{guid}-{i}", None] for i in range(bundles)],
        "rendered_morphs": list(forms or [f"{guid}{i}" for i in range(bundles)]),
        "gloss": gloss,
        "category_label": "v",
        "parser_evaluated": parser_evaluated,
        "evaluator": evaluator if opinion in ("approves", "disapproves") else None,
        "evaluated_at": evaluated_at if opinion in ("approves", "disapproves") else None,
        "in_segment": in_segment,
    }


def line(index, wordform, analyses, human=()):
    return {
        "index": index,
        "wordform": wordform,
        "parse": {
            "parsed": bool(analyses),
            "analysis_count": len(analyses),
            "analyses": list(analyses),
            "human_analyses": list(human),
            "error_message": None,
            "parse_time_ms": 1,
        },
    }


PARSED_STATE = {
    "parser_has_ever_run": True, "analyses_total": 10, "parser_created_analyses": 6,
    "human_opinion_analyses": 3, "indeterminate_analyses": 0, "truncated": False,
}

NEVER_PARSED_STATE = dict(PARSED_STATE, parser_has_ever_run=False, parser_created_analyses=0)


def every_case_lines() -> List[Dict[str, Any]]:
    """One word per oracle case, plus a pairing and a lexicalized form."""
    return [
        line(0, "approved", [parser_analysis("a")],
             [stored("g-affirmed", opinion="approves", in_segment=False)]),
        line(1, "inuse", [parser_analysis("b")],
             [stored("g-inuse", opinion="approves", in_segment=True)]),
        line(2, "disliked", [parser_analysis("c")],
             [stored("g-disliked", opinion="disapproves")]),
        line(3, "unchecked", [parser_analysis("d")],
             [stored("g-unchecked", opinion="noopinion", parser_evaluated=True)]),
        line(4, "glossed", [parser_analysis("e", glosses=["", "house"])],
             [stored("g-meaning", bundles=0, gloss="house")]),
        line(5, "begun", [parser_analysis("f")],
             [stored("g-sketched", bundles=3, complete=1)]),
        line(6, "understand",
             [parser_analysis("u", glosses=["beneath", "stand"], forms=["under", "stand"])],
             [stored("g-lex", bundles=0, gloss="comprehend")]),
    ]


def write_run(record_dir, lines, *, project_state=PARSED_STATE):
    """A finished batch run on disk, as the batch path writes it."""
    from flextoolsmcp.server.parse.record import RunRecord
    from flextoolsmcp.server.parse.stages import RunStage

    words = [l["wordform"] for l in lines]
    record = RunRecord.create(
        project_name="P", words_total=len(words), record_dir=record_dir, words=words,
        scope_fingerprint={"scope_kind": "words"}, engine_at_submission="HC",
        project_state=project_state,
    )
    for l in lines:
        record.append_result(l)
    record.set_stage(RunStage.COMPLETED)
    return record


def summary_response(run_id, **args) -> Dict[str, Any]:
    """The whole parse_log summary response, as the caller receives it."""
    from flextoolsmcp.server.handlers import parse as parse_handler

    out = asyncio.run(parse_handler.handle_flextools_parse_log(
        dict({"run_id": run_id, "section": "summary"}, **args)
    ))
    return json.loads(out[0].text)


def find_report(response: Dict[str, Any]) -> Dict[str, Any]:
    """The report block wherever the envelope nests the summary."""
    stack = [response]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "report" in node and isinstance(node["report"], dict) and "oracle" in node["report"]:
                return node["report"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    raise AssertionError("no report in the response")


def walk(node, path=()):
    """Yield (path, key, value) for every dict entry and list item."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from walk(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield path, i, value
            yield from walk(value, path + (i,))
