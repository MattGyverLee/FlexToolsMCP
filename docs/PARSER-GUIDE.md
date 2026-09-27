# Parser checks: a field linguist's guide

This page is for someone editing a grammar in FieldWorks (FLEx) who wants an
AI assistant (Claude Code, Copilot, Gemini CLI, or similar, talking to this
MCP server) to run the parser for them -- try a word, parse a text, see
whether a grammar edit helped, and (carefully) file the results back into
the project. It is written for the person typing requests to the assistant,
not for someone reading the server's source code. Where a tool name appears,
it is because you will see it in the assistant's replies, and it is
explained in plain language the first time it comes up.

If you want the developer-facing contract (exact fields, error shapes,
schemas), see [docs/TOOL-CONTRACT.md](TOOL-CONTRACT.md). This page only
tells you what to ask for and what the answers mean.

## What the parser checks are for

FieldWorks' HermitCrab parser tries to break a word down into its pieces
(root, prefixes, suffixes, and so on) using the grammar you have built --
your parts of speech, affix rules, phonological rules, and lexicon. When a
word does not parse the way you expect, or parses in *too many* ways, the
question is usually "what in my grammar is causing this?" -- and until now,
answering that meant opening FLEx, running Parse Words in Text or Try A
Word by hand, and reading the trace yourself.

These tools let your assistant run that same parser for you, on your
behalf, and describe what happened in words. The basic loop most people use
is:

1. **Try a word** that fails, or parses unexpectedly, and ask the assistant
   why.
2. **Edit the grammar** in FLEx based on what you learn (a new allomorph, a
   loosened environment, a new affix rule).
3. **Try the word again** -- or parse a whole text or corpus -- and **read
   the diff** against the earlier run to see whether the edit actually
   helped, and whether it broke anything else.
4. Once you are happy with a batch of results, **file them into the
   project** so FLEx's own analyses reflect what the parser now produces --
   this is the one step in this whole guide that writes anything, and it is
   deliberately hard to do by accident.

Everything up through step 3 only reads your project. Nothing is written
until you explicitly ask for step 4, and even then you get a chance to
review and back out before anything changes.

## Prerequisites

- **FieldWorks 9**, with the project's active parser set to **HermitCrab**
  (Words > Parser > Choose Parser in FLEx). These tools only support
  HermitCrab; a project configured for XAmple is refused before anything
  runs, with a clear message naming which engine is configured and which
  is supported.
- Ask your assistant to run **`flextools_health`** first if anything below
  seems unavailable. It tells you, without opening your project, whether
  the parser is usable at all on this machine and why not. See "Reading
  flextools_health's parser section" below for what each part means.

## (a) Try a word

Ask something like: *"Try the word `berjalan` against my grammar"* or *"Why
doesn't `nyusahne` parse?"* Your assistant will call **`flextools_try_word`**
with your project and the word. There are three ways to ask, matched to
three different questions:

- **A quick yes/no.** "Does this word parse at all?" -- cheapest, and
  honest about its limits: if the word fails, you're told only that it
  failed, not why. Ask for a reason next if you need one.
- **The full explanation.** "I have no idea why this fails -- show me
  everything." This runs the parser's complete trace and is the slowest of
  the three, because it explores every possibility with no guidance from
  you. Use it when you don't have a guess.
- **Test a hypothesis.** "I think this word is *root* + *-lah* + *-kah* --
  does the parser agree?" You give the pieces (by their dictionary
  headword, optionally with a specific sense if the headword has several
  meanings), and the assistant asks the parser to trace *exactly that*
  decomposition, nothing else. This is the fastest of the three, because it
  doesn't have to search -- and it's the right choice whenever you already
  have a guess about how a word should break down.

You do not type a segmented spelling like `root-lah-kah` -- you name the
pieces by their lexicon entries, because the tool has no way to guess a
segmentation from raw spelling. If a piece you named doesn't match anything
in the lexicon, matches more than one homograph, or matches an entry with
no usable grammatical analysis, you're told exactly which piece and why,
and no parse is attempted -- fix the piece and try again.

**If a word (or a quick timing check) takes more than a few seconds**, you
won't be left waiting: you get a handle back right away and the work keeps
going in the background. Ask the assistant to check on it (this polls
**`flextools_parse_status`**) whenever you like.

**If your grammar itself seems slow** -- individual words taking a long
time even one at a time -- ask the assistant to measure it (a timed,
yes/no-only run) rather than trace it; a trace of a slow grammar just times
the tracer as well as the grammar. A grammar that is measurably slow is
usually a sign to run the static grammar scan
(**`flextools_grammar_health`**) instead of tracing single words: it looks
at your grammar's structure directly (things like affixes that can attach
in an unbounded number of ways, or duplicate feature combinations) and
reports suspect patterns with examples, without parsing anything at all.

## (b) Parse a text, or a whole corpus, in the background

Trying single words is fine for spot-checks, but most real grammar work
means parsing a lot of text at once and looking at the overall picture. Ask
something like: *"Parse the whole text 'Frog Story'"*, *"Parse everything
tagged as narrative"*, or *"Parse the whole project."* Your assistant calls
**`flextools_parse_text`**, which:

- Resolves what you asked for (a specific text, a genre, or the whole
  project) into the actual list of distinct words involved, most-frequent
  first;
- Parses every one of them against your grammar, in the background, and
  hands back a run identifier right away rather than making you wait; and
- By default, **writes nothing to your project** -- this is a read-only
  measurement of what the parser currently does with your text.

You can also hand it an explicit list of words instead of a text or genre,
which is handy for testing a small, specific set.

While it runs (which can take a while on a large corpus), ask the assistant
to:
- **Check progress** (`flextools_parse_status`) -- it tells you which stage
  the run is in (still loading the grammar, actively parsing, filing
  results, or done), and how many words are finished so far. Loading the
  grammar is called out separately from parsing because on a large project
  it can itself take a while, and it's the step most likely to run out of
  memory.
- **Read the run's record** (`flextools_parse_log`) -- the resolved word
  list, the per-word results so far, and (for a finished batch) a summary
  report that flags a handful of corpus-level patterns worth a second look
  -- always phrased as candidates for you to consider, never as
  automatically-acted-on decisions.
- **Cancel it** (`flextools_parse_cancel`) if it's taking too long or you
  started the wrong thing. It stops at the next word boundary rather than
  immediately, and everything completed up to that point stays readable.

If you try a single word in the middle of a big background batch, the
single word jumps the queue and is answered right away, using the same
already-loaded grammar; the batch just picks back up where it left off
once your word is done.

**Releasing the worker.** Trying a word or parsing a text keeps a
background helper process attached to your project for a while afterward
(so the next request doesn't have to reload the grammar from scratch), and
that process holds the same kind of lock FLEx itself takes when it opens a
project. Normally you don't need to think about this -- it lets go on its
own after a period of inactivity, and starting a write also lets go of it
automatically. But if you want to hand the project back to FLEx (or another
tool) right away, ask the assistant to release it explicitly
(**`flextools_parse_release`**). It will refuse if a parse is genuinely
still running (pointing you at cancel instead), and it's a safe no-op if
nothing is holding the project at all.

## (c) Read the diff: did my grammar edit help?

This is the heart of the edit-and-check loop. Once you have two background
runs over the **same** text or word set -- one from before a grammar
change, one from after -- ask: *"Did that grammar edit help?"* or *"Compare
these two runs."* Your assistant calls **`flextools_parse_diff`** with the
two run identifiers, and every word lands in exactly one of four groups,
decided strictly by *which* analyses it now gets, never by how many:

- **Fixed** -- didn't parse before, parses now.
- **Broken** -- parsed before, doesn't parse now. Worth checking even on a
  change you expected to only help.
- **Changed** -- parsed both times, but with different analyses. A word
  going from one reading to seven counts as changed: it still parses, but
  your grammar got looser, which may or may not be what you wanted.
- **Unchanged** -- identical analyses both times.

There's also a separate, quieter category: words whose analyses *look* the
same both times but were actually built from different lexicon entries
underneath. That means something in your *lexicon* changed, not your
grammar -- worth knowing, but a different kind of change than the parse
categories above.

**One caveat that catches people out:** if FieldWorks still has the project
open when you run the "after" parse, your grammar edit might not be saved
to disk yet, and the comparison will say so rather than silently comparing
against stale data. Save (or close) the project in FLEx, then parse again.

The two runs being compared have to describe the same scope -- the same
text or genre, the same word limit, the same writing system, the same
engine. If they don't, you're told exactly which of those differ; you can
still ask for a comparison of just the words the two runs have in common,
but the tool will say plainly that it's not comparing the full scope.

## (d) Filing results into the project -- the one write path

Everything above only reads your project. Filing is different: it takes
what the parser produced in a background run and writes it into FLEx, the
same way FLEx's own **Parse Words in Text** command does. This is the one
place in the whole parser-check feature where anything changes on disk, and
it is built to be hard to trigger by accident.

**What filing actually does, honestly stated:** for every word in the
run's scope, the parser's analyses are created or re-confirmed. And --
this is the part to read carefully -- **any existing analysis for those
words that neither the parser produces any more nor a person has personally
approved, and that is not currently used anywhere in a text, gets deleted.**
That mirrors exactly what FLEx's own Parse Words in Text does; it is not
something this tool invented. It means that if your grammar edit made the
parser stop producing an old, unused, unapproved analysis, filing will
remove that stale analysis -- which is usually exactly what you want after
a grammar improvement, but it is a real deletion, and it cannot be undone
except by restoring a backup (or, for a project kept in Send/Receive,
discarding your local copy and re-downloading it).

Because of that, filing always goes through the same sequence, and there is
no setting, flag, or shortcut that skips any of these steps:

1. **Ask to file** ("file the results of that run into the project").
   Nothing is written yet. What comes back is a **preview**: a concrete,
   project-specific plan showing exactly which words are in scope, how many
   analyses *may* be deleted for each one (a real number, computed from
   your project -- including 0 where nothing is at risk), how many
   existing analyses that a *person* had specifically marked as wrong will
   instead be recorded as approved by this run (because they are still in
   use in a text), and whether the grammar currently loads cleanly enough
   to file at all. This preview also says whether a backup is expected to
   be taken.
2. **Confirm it.** Only after you've looked at the preview and said yes
   does the assistant resubmit it, referencing the specific plan you were
   shown. If anything about the project has changed in the meantime (a
   different word would now be affected, the grammar's standing changed),
   you get a **new** preview instead of a filing run -- your confirmation
   only ever applies to the exact plan you saw.
3. **A backup is attempted first, every time** (there is no setting that
   skips it): before filing writes anything, the server backs up your
   project file. If a backup genuinely can't be taken -- for example, not
   enough free disk space -- filing still goes ahead, but you get a loud,
   explicit warning that says there is no way back if something goes
   wrong. See [docs/RECOVERY.md](RECOVERY.md) for how backups are stored
   and how to restore one.
4. **Only then does filing run**, word by word, and the run's record keeps
   an entry for every analysis it deletes, so you can always see afterward
   exactly what was removed and why.

**The refuse-to-file safety gate.** Filing checks your grammar's health
before it writes anything, and it refuses outright -- with no override --
if: the parser can't be built at all; this grammar load logged errors that
an earlier read-only parse of the same scope did not; or fewer lexicon
entries are reaching the grammar than they were before (something FLEx's
own loader does silently, without telling you). The only way past any of
these is to run a fresh read-only parse of the same scope first, which
re-establishes a clean baseline to measure against -- there is no setting
that bypasses this check.

A few other things worth knowing about filing:
- It requires a session where write access has been explicitly turned on --
  the same permission any other write in this MCP requires.
- Only one filing run can be in progress on a project at a time; a second
  attempt is refused (not queued) while the first is still going.
- If you cancel a filing run partway through, everything filed *before* the
  cancel stays filed -- cancelling stops new writes, it does not undo old
  ones.
- If FLEx has the project open with sharing turned on, filing runs
  alongside it as a peer; make sure FLEx's own parser isn't also running on
  the same project at the same time, since the two writing at once is not
  guarded against. See [docs/SHARED-MODE.md](SHARED-MODE.md).

## (e) The sandbox: speculative edits without touching your project

Sometimes you want to try a grammar change that you're not sure about yet,
without touching your real project at all -- not even read-only access
while you experiment. Ask the assistant to *"set up a sandbox from my
project"* or *"try this in a sandbox."* This uses **`flextools_parse_sandbox`**,
which:

- Makes a copy of your grammar (exported the same way FieldWorks itself
  would export it) into a **named sandbox** on disk, separate from your
  project entirely.
- Parses words against that sandbox using FieldWorks' own bundled parsing
  engine -- the same one Try A Word uses -- running in its own separate
  worker, with your live project never opened at all.
- Lets you edit the sandbox's exported grammar file as speculatively as you
  like and re-parse to see the effect, with zero risk to your actual
  project.

You can also **save a list of words as a named corpus** from a completed
sandbox run, so you can re-run the same set of words against a later
sandbox edit without retyping the list, and ask the assistant to **list**
what sandboxes and corpora you already have. Sandboxes and corpora are
files that belong to you, kept outside any project folder; nothing about
managing them ever touches your live project.

## Reading flextools_health's parser section

If you ask the assistant to run **`flextools_health`**, part of the answer
is a `parser` section describing whether the parser tools are usable at
all on this machine, before you try anything project-specific. Here is what
each piece means and what to do about it:

| What you'll see | What it means | What to do |
|---|---|---|
| **Read: ready** | Trying a word and parsing text (steps a-c above) can work. | Nothing -- proceed. |
| **Read: unavailable** | The parser's core component could not be found or loaded on this machine at all -- usually a broken or missing FieldWorks install. Nothing in steps (a)-(c) will work. | Repair or reinstall FieldWorks 9. |
| **Write: ready** | Filing (step d) can work, on top of read being ready. | Nothing -- proceed. |
| **Write: unavailable**, but read is ready | `flextools_health` never opens a project, so it cannot tell whether this project has run HermitCrab before -- what it is actually reporting here is that a piece of the filing component itself (`ParseFiler.ProcessParse`) is missing from this FieldWorks install. Everything read-only (try a word, parse text, read diffs) is unaffected. | Repair or reinstall FieldWorks 9. (You may separately hit the "never run before" case, but you'll see it as the `parser_agent_missing` error when you actually try to file -- see the error table below -- not as something `flextools_health` can detect ahead of time.) |
| **Sandbox: ready** | Step (e), the sandbox, can work; it lists the two FieldWorks components it depends on (the bundled HermitCrab engine and the grammar-export tool) as both present. | Nothing -- proceed. |
| **Sandbox: unavailable**, listing a missing component | One of the two FieldWorks pieces the sandbox needs isn't present in this FieldWorks install. | Repair or reinstall FieldWorks 9; the report names which piece is missing. |
| **`active_engine`** | `flextools_health` never opens a project, so this field is unconditionally blank in its output regardless of what's open in your session -- it is purely informational and never decides anything by itself. The actual "wrong engine" refusal happens per-call (see `parser_engine_mismatch` below), reading the project directly, not from this field. | Nothing to act on directly. |
| **The version numbers under "detected"** (parser version, FieldWorks engine version, etc.) | Reported for your own reference and for bug reports -- these are informational only. Nothing in this tool compares them against a required minimum, so an older or newer version showing here is not itself a problem. | Include them if you're reporting a bug. |
| **The suggested next steps alongside the parser section** | Whenever something above is unavailable, `flextools_health` also lists one or more concrete next actions (in plain language, sometimes naming a tool to run) rather than leaving you to guess. | Follow the suggested action; it's tailored to exactly what's missing. |

## When something goes wrong

If a parser tool refuses instead of answering, the message names a specific
reason. Here is what each one means and what to do.

| Error code | Plain meaning | What to do |
|---|---|---|
| `parser_engine_mismatch` | This project's active parser is not HermitCrab (commonly it's set to XAmple). These tools only work with HermitCrab. | In FLEx: Words > Parser > Choose Parser, switch to HermitCrab, then retry. |
| `parser_core_missing` | The parser's core component isn't usable on this machine at all -- absent, from a mismatched FieldWorks install, missing a piece these tools need, or it failed to load. | Repair or reinstall FieldWorks 9. Run `flextools_health` for more detail on which of those it is. |
| `parser_agent_missing` | Filing specifically is unavailable because this project has never had HermitCrab run against it, even once, from inside FLEx -- so there's no record of HermitCrab as an "owner" of analyses yet. Reading and trying words are unaffected. | Open the project in FLEx, run the parser once from the Words > Parser menu (Parse Words in Text, or Try A Word), then retry filing. |
| `parser_tool_missing` | The sandbox specifically needs a FieldWorks-bundled engine component or its grammar-export tool, and one of the two is missing from this FieldWorks install. | Repair or reinstall FieldWorks 9. |
| `parse_morph_unresolved` | You proposed a decomposition (a "restricted" try-a-word test) and one of the pieces you named doesn't resolve cleanly -- either nothing in the lexicon matches it, several homographs match and it's ambiguous which one you mean, or the matching entry has no usable grammatical analysis. No parse was attempted. | Check the spelling of that piece, add a sense number if it's a homograph, or check that the entry has an analysis (part of speech / MSA) attached. |
| `parse_run_not_found` | The run identifier you asked about doesn't exist (maybe mistyped, or from a much earlier session that's been cleaned up). | The message lists the run identifiers that *do* exist -- pick from those, or start a new run. |
| `parse_job_cancelled` | You tried to act on a run (like cancelling it again) that has already ended. | Nothing to fix -- the run is already done; check its results with `flextools_parse_log` instead. |
| `parse_scope_empty` | The text, genre, or word list you asked to parse didn't match anything in the project. | Double-check the exact name; the response lists anything that *did* partially match, to help tell a typo from a genuinely empty scope. |
| `parse_scope_ambiguous` | The genre or text name you gave matches more than one thing in the project. | The response lists every candidate it matched -- pick the one you meant and be more specific (e.g. use the full text name instead of an abbreviation). |
| `parse_scope_mismatch` | You asked to compare (diff) two runs that don't describe the same underlying scope -- different text, genre, word limit, writing system, or engine. | Either re-parse with a matching scope, or explicitly ask to compare anyway (accepting that only the words the two runs share in common will be compared). |
| `parser_filing_in_progress` | A filing run is already going on this project; a second filing request can't start until it finishes. | Wait, and check on the in-progress run with `flextools_parse_status` using the run identifier the message gives you. |
| `project_locked` | Filing needs to open the project for writing, but FieldWorks (or another process) is holding it exclusively -- or, for `flextools_parse_release`, a parse is still genuinely running, so the worker can't be released this way. | Close the project in FLEx, or wait for the other holder to finish; if sharing is turned on, filing can run alongside FLEx as a peer, but make sure FLEx's own parser isn't running on the project at the same time. For a release refusal specifically, use `flextools_parse_cancel` on the run named in the message instead. |
| `grammar_load_unclean` | Filing refused because your grammar isn't in a state it's willing to file from: either the parser couldn't be built at all, this load produced new errors a prior read-only parse of the same scope didn't have, or fewer lexicon entries are reaching the grammar than before (which FLEx's own loader does silently). | Fix the underlying grammar problem the message points at, then run a fresh read-only parse of the same scope to re-establish a clean baseline, and try filing again. There is no way to skip this check. |
| `parser_timeout` | A sandbox run hit its time limit before finishing. | Everything completed before the timeout is still readable. Either raise the time limit for next time, or narrow the word list. |
| `parser_job_failed` | A sandbox run failed outright -- out of memory, the worker crashed, the exported grammar wouldn't load into the engine, or an internal id mapping was invalid. | The message names which of these it was and points at a log path with more detail; for a bad export, try re-creating the sandbox. |
| `parser_config_failed` | Exporting your project's grammar into a sandbox failed. | The message includes the tail of the export tool's own output and a log path -- often points at something specific in the grammar the exporter couldn't handle. |
| `parse_sandbox_refused` | A sandbox or corpus request was refused before anything was created -- an invalid or already-used name, a corpus or sandbox that doesn't exist, an invalid word file, or not enough free disk space for the copy. | The message's reason field says exactly which; fix that and retry (e.g. pick a different sandbox name, or free up disk space). |

If you ever see a message that doesn't match any of the above, or a
response that surprises you, running `flextools_health` and sharing its
output with whoever maintains this server is the fastest way to get help.

## See also

- [docs/TOOL-CONTRACT.md](TOOL-CONTRACT.md) -- the full response envelope
  and error-code contract, for anyone building on top of these tools.
- [docs/SHARED-MODE.md](SHARED-MODE.md) -- what works, and what's refused,
  when FLEx has the project open at the same time as this server.
- [docs/RECOVERY.md](RECOVERY.md) -- how the automatic pre-write backup
  works and how to restore one.
