#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Driving FieldWorks' `ParseFiler` headlessly (parser-check CP4, FR-018,
FR-019; research R-03; tasks.md T055, a TRIPWIRE).

The fakes below model the real classes' behaviour exactly where it matters:

  * `ParseFiler.ProcessParse` only ENQUEUES: it adds the word to the filer's
    private work queue and asks its `IdleQueue` to run `UpdateWordforms`
    later (`ParseFiler.cs:128-133`);
  * `UpdateWordforms` returns False and LEAVES the work queued when a unit of
    work is already open (`CanStartUow`, `:165-166`); otherwise it files
    everything queued, in one go (`:171-174`);
  * `TaskReport`'s constructor calls its handler immediately, so a null
    handler would throw (`TaskReport.cs:37-42`).

THE TRIPWIRE: a word the filer declines must NOT be filed by the next word's
pump. A single long-lived filer fails this -- the declined word sits in its
private queue and is filed silently with the next one, later, out of order
and outside its own liveness check. A fresh filer per word passes.
"""

import pytest

from flextoolsmcp.server.filing import filer


class FakeTask:
    def __init__(self, delegate, parameter=None):
        self.Delegate = delegate
        self.Parameter = parameter


class FakeIdleQueue:
    constructed = []

    def __init__(self):
        self.IsPaused = False
        self._tasks = []
        FakeIdleQueue.constructed.append(self)

    def Add(self, priority, delegate):  # noqa: N802 -- the CLR's name
        # update=true: replaces an existing entry for the same delegate.
        self._tasks = [t for t in self._tasks if t.Delegate is not delegate]
        self._tasks.append(FakeTask(delegate))

    def Remove(self, task):  # noqa: N802
        self._tasks.remove(task)
        return True

    def __iter__(self):
        return iter(list(self._tasks))


class FakeProject:
    """The project the filer writes into: which words got filed, in order."""

    def __init__(self):
        self.filed = []
        self.uow_open = False


class FakeFiler:
    constructed = []

    def __init__(self, cache, property_table, handler, idle_queue, agent):
        assert handler is not None, "TaskReport calls the handler at once: never null"
        assert idle_queue is not None, "a real stand-in for the idle queue, never null"
        self.cache = cache
        self.property_table = property_table
        self.idle_queue = idle_queue
        self.agent = agent
        self._work = []
        FakeFiler.constructed.append(self)

    def ProcessParse(self, wordform, priority, result, check_parser):  # noqa: N802
        assert self.idle_queue.IsPaused is True, "the queue must be paused before use"
        self._work.append((wordform, result))
        self.idle_queue.Add("Low", self._update_wordforms)
        return True

    def _update_wordforms(self, parameter):
        if self.cache.uow_open:
            return False                      # CanStartUow false: work STAYS queued
        for wordform, _result in self._work:
            self.cache.filed.append(wordform)
        self._work.clear()
        return True


class Surface:
    ParserPriority = type("ParserPriority", (), {"Low": "Low"})

    def __init__(self):
        self.handlers = []

    def IdleQueue(self):  # noqa: N802
        return FakeIdleQueue()

    def ParseFiler(self, *args):  # noqa: N802
        return FakeFiler(*args)

    def task_report_handler(self):
        handler = object()
        self.handlers.append(handler)
        return handler


@pytest.fixture(autouse=True)
def _reset():
    FakeIdleQueue.constructed.clear()
    FakeFiler.constructed.clear()


def test_the_queue_is_real_and_paused_and_the_handler_is_not_null():
    project, surface = FakeProject(), Surface()
    out = filer.file_one(surface=surface, cache=project, agent="HC-AGENT",
                         wordform="pukul", parse_result="R")
    assert out.outcome == "filed"
    assert FakeIdleQueue.constructed[0].IsPaused is True
    assert surface.handlers and surface.handlers[0] is not None
    assert project.filed == ["pukul"]


def test_the_filer_gets_the_agent_it_is_given_and_a_null_property_table():
    project, surface = FakeProject(), Surface()
    filer.file_one(surface=surface, cache=project, agent="HC-AGENT",
                   wordform="pukul", parse_result="R")
    built = FakeFiler.constructed[0]
    assert built.agent == "HC-AGENT"
    assert built.property_table is None, "null -> CheckParserUpdatesAnalyses defaults true"


def test_a_decline_is_filer_declined():
    project, surface = FakeProject(), Surface()
    project.uow_open = True
    out = filer.file_one(surface=surface, cache=project, agent="A",
                         wordform="pukul", parse_result="R")
    assert out.outcome == "filer_declined"
    assert project.filed == []


def test_a_declined_word_is_not_filed_by_the_next_words_pump():
    """THE TRIPWIRE. One filer per word: the decline cannot leak."""
    project, surface = FakeProject(), Surface()
    project.uow_open = True
    first = filer.file_one(surface=surface, cache=project, agent="A",
                           wordform="declined", parse_result="R1")
    project.uow_open = False
    second = filer.file_one(surface=surface, cache=project, agent="A",
                            wordform="next", parse_result="R2")
    assert first.outcome == "filer_declined" and second.outcome == "filed"
    assert project.filed == ["next"], (
        "the declined word must not be filed later, out of order, by another word's pump"
    )
    assert len(FakeFiler.constructed) == 2, "a fresh filer per word"


def test_the_pump_removes_each_task_before_running_it():
    project, surface = FakeProject(), Surface()
    filer.file_one(surface=surface, cache=project, agent="A", wordform="w", parse_result="R")
    assert list(FakeIdleQueue.constructed[0]) == []


# ---------------------------------------------------------------------------
# R-03 -- every bound member is probed
# ---------------------------------------------------------------------------


class _Param:
    pass


class _Member:
    def __init__(self, name, arity):
        self.Name = name
        self._arity = arity

    def GetParameters(self):  # noqa: N802
        return [_Param() for _ in range(self._arity)]


class _Type:
    def __init__(self, ctors=(), methods=(), props=()):
        self._ctors = [_Member(".ctor", n) for n in ctors]
        self._methods = [_Member(n, a) for n, a in methods]
        self._props = set(props)

    def GetConstructors(self):  # noqa: N802
        return self._ctors

    def GetMethods(self):  # noqa: N802
        return self._methods

    def GetProperty(self, name):  # noqa: N802
        return name if name in self._props else None

    def GetField(self, name):  # noqa: N802
        return None


def _complete_namespace():
    return {
        "ParseFiler": _Type(ctors=[5], methods=[("ProcessParse", 4), ("ProcessParse", 4)]),
        "IdleQueue": _Type(ctors=[0], methods=[("Remove", 1), ("GetEnumerator", 0)],
                           props=["IsPaused"]),
        "IdleQueueTask": _Type(props=["Delegate", "Parameter"]),
        "ParseAnalysis": _Type(methods=[("MatchesIWfiAnalysis", 1)]),
        "ParseResult": _Type(props=["IsValid"]),
    }


def test_a_complete_surface_probes_clean():
    assert filer.probe_bound_members(_complete_namespace()) == []


def test_a_missing_member_is_named():
    namespace = _complete_namespace()
    namespace["ParseAnalysis"] = _Type(methods=[])
    assert filer.probe_bound_members(namespace) == ["ParseAnalysis.MatchesIWfiAnalysis(1)"]


def test_a_constructor_of_the_wrong_arity_is_missing():
    namespace = _complete_namespace()
    namespace["ParseFiler"] = _Type(ctors=[4], methods=[("ProcessParse", 4)])
    assert "ParseFiler..ctor(5)" in filer.probe_bound_members(namespace)


def test_a_missing_type_names_every_member_of_it():
    namespace = _complete_namespace()
    del namespace["IdleQueue"]
    missing = filer.probe_bound_members(namespace)
    assert [m for m in missing if m.startswith("IdleQueue.")] == [
        "IdleQueue..ctor(0)", "IdleQueue.IsPaused", "IdleQueue.Remove(1)",
        "IdleQueue.GetEnumerator(0)",
    ]
