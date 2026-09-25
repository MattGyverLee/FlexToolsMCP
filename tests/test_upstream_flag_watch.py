"""scripts/upstream_flag_watch.py -- the watch that says when a temporary
curated deprecation (DoNotUseForParsing, LT-22810) may be ready to lift.

GitHub is never contacted: ``_search`` and ``_gh`` are replaced with fakes.
"""

import importlib.util
import json
import os

import pytest

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "upstream_flag_watch.py",
)
DEP_ID = "lexentry-donotuseforparsing"


@pytest.fixture
def watch():
    spec = importlib.util.spec_from_file_location("upstream_flag_watch", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_search(code=None, issues=None, commits=None):
    def search(kind, query):
        if kind == "code":
            repo = query.split("repo:", 1)[1]
            return [i for i in (code or []) if i["_repo"] == repo]
        return {"issues": issues, "commits": commits}[kind] or []
    return search


def _baseline_code(watch):
    repos = watch.CURATED_DEPRECATIONS[DEP_ID]["upstream_watch"]["repos"]
    return [{"_repo": r, "path": p, "html_url": f"https://x/{p}"}
            for r, paths in repos.items() for p in paths]


def test_dnufp_is_watched_and_tracked(watch):
    dep = watch.watches()[DEP_ID]
    assert dep["tracking"]["ticket"] == "LT-22810"
    assert set(dep["upstream_watch"]["repos"]) == {
        "sillsdev/FieldWorks", "sillsdev/liblcm", "sillsdev/machine"}


def test_tracking_is_not_leaked_into_index_annotation(watch):
    from flextoolsmcp.curated_deprecations import deprecation_record
    rec = deprecation_record(DEP_ID)
    assert "tracking" not in rec and "upstream_watch" not in rec


def test_baseline_only_is_quiet(watch, monkeypatch):
    baseline_prs = [{"html_url": u, "title": "old", "state": "closed", "pull_request": {},
                     "repository_url": "https://api.github.com/repos/sillsdev/liblcm"}
                    for u in watch.CURATED_DEPRECATIONS[DEP_ID]["upstream_watch"]["baseline_refs"]]
    monkeypatch.setattr(watch, "_search", _fake_search(_baseline_code(watch), baseline_prs))
    assert watch.scan(DEP_ID, watch.CURATED_DEPRECATIONS[DEP_ID]) == []
    assert watch.main([]) == 0


def test_new_parser_code_pr_and_commit_are_findings(watch, monkeypatch):
    code = _baseline_code(watch) + [{
        "_repo": "sillsdev/FieldWorks",
        "path": "Src/LexText/ParserCore/HCLoader.cs",
        "html_url": "https://github.com/sillsdev/FieldWorks/blob/main/Src/LexText/ParserCore/HCLoader.cs",
    }]
    pr = [{"html_url": "https://github.com/sillsdev/FieldWorks/pull/999",
           "title": "LT-22810: honour DoNotUseForParsing", "state": "open",
           "pull_request": {}, "repository_url": "https://api.github.com/repos/sillsdev/FieldWorks"}]
    commit = [{"html_url": "https://github.com/sillsdev/machine/commit/abc",
               "commit": {"message": "Skip DoNotUseForParsing entries\n\nbody"},
               "repository": {"full_name": "sillsdev/machine"}}]
    monkeypatch.setattr(watch, "_search", _fake_search(code, pr, commit))
    findings = watch.scan(DEP_ID, watch.CURATED_DEPRECATIONS[DEP_ID])
    assert [f["kind"] for f in findings] == ["code", "pr", "commit"]
    assert findings[0]["title"] == "Src/LexText/ParserCore/HCLoader.cs"
    assert findings[2]["title"] == "Skip DoNotUseForParsing entries"
    assert watch.main([]) == 1


def test_search_failure_is_exit_2_not_a_verdict(watch, monkeypatch):
    def boom(kind, query):
        raise watch.WatchError("rate limited")
    monkeypatch.setattr(watch, "_search", boom)
    assert watch.main([]) == 2


class _FakeGh:
    def __init__(self, issues, labels=("upstream-flag-watch",)):
        self.issues, self.labels, self.calls = issues, list(labels), []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        if args[:2] == ["label", "list"]:
            return json.dumps([{"name": n} for n in self.labels])
        return ""

    def verbs(self):
        return [tuple(a[:2]) for a in self.calls]


F1 = {"key": "code:sillsdev/FieldWorks:HCLoader.cs", "kind": "code",
      "repo": "sillsdev/FieldWorks", "title": "HCLoader.cs", "url": "https://x/1"}
F2 = {"key": "pr:https://x/2", "kind": "pr", "repo": "sillsdev/FieldWorks",
      "title": "PR (open)", "url": "https://x/2"}


def test_first_finding_creates_issue_with_ticket_and_unblock_steps(watch, monkeypatch):
    gh = _FakeGh([], labels=())
    monkeypatch.setattr(watch, "_gh", gh)
    dep = watch.CURATED_DEPRECATIONS[DEP_ID]
    assert watch.sync_issue(DEP_ID, dep, [F1], None) == "created"
    assert ("label", "create") in gh.verbs()
    create = next(a for a in gh.calls if a[:2] == ["issue", "create"])
    title, body = create[create.index("--title") + 1], create[create.index("--body") + 1]
    assert "LT-22810" in title and f"[{DEP_ID}]" in title
    assert "jira.sil.org/browse/LT-22810" in body
    assert "curated_deprecations.py" in body and "--apply" in body
    assert watch._seen_keys(body) == [F1["key"]]


def test_existing_issue_comments_only_on_new_findings(watch, monkeypatch):
    dep = watch.CURATED_DEPRECATIONS[DEP_ID]
    title = watch._issue_title(DEP_ID, dep)
    old_body = watch.render_markdown(DEP_ID, dep, [F1]) + \
        f"\n<!-- upstream-flag-watch:seen={json.dumps([F1['key']])} -->"
    issue = [{"number": 7, "title": title, "body": old_body}]

    gh = _FakeGh(issue)
    monkeypatch.setattr(watch, "_gh", gh)
    assert watch.sync_issue(DEP_ID, dep, [F1], None) == "refreshed #7 (nothing new)"
    assert ("issue", "comment") not in gh.verbs()

    gh = _FakeGh(issue)
    monkeypatch.setattr(watch, "_gh", gh)
    assert watch.sync_issue(DEP_ID, dep, [F1, F2], None) == "commented on #7"
    comment = next(a for a in gh.calls if a[:2] == ["issue", "comment"])
    text = comment[comment.index("--body") + 1]
    assert F2["url"] in text and F1["url"] not in text
