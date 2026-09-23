# Review notes: parser-check CP3

Pattern-audit sweeps the `lex-qc` gate blocks on, plus implementation findings
worth a reviewer's attention. One section per sweep task.

---

## T030 -- first-element-only reads of a multi-valued LCM collection (FR-006 shape)

**Date**: 2026-09-22 · **Scope**: `src/flextoolsmcp/` (code and the bundled index it serves)

**The shape**: a read that takes the first element of a collection that can
hold several, where the count matters. The anchor case is
`TextOperations.GetGenre` -- first of `GenresRC` -- which made a text tagged
`[Narrative, Folklore]` invisible to "Folklore".

**The fix at the anchor**: `server/parse/scope.py` reads genres only through
`genres_of` -> `TextOperations.GetGenres` (the full collection). Pinned by
`tests/test_parse_scope.py::test_text_with_two_genres_is_found_by_its_second_genre`
(the double's `GetGenre` returns the first genre, as the library does, so an
implementation that reaches for it fails) and by
`test_scope_module_does_not_call_the_first_genre_only_read`.

**Method**: grep over `src/flextoolsmcp/` for `GetGenre(`, `[0]` on
collections, `.First(`/`FirstOrDefault`, `next(iter(...))`, `OS/OC/RC/RS)[0]`,
and singular `Get*` reads of multi-valued fields; each hit read in context.

### Siblings

| Location | What | Confidence | Disposition |
|---|---|---|---|
| `index/python/common_patterns_flexicon-v4.9.0.json:824` (and the matching `flexicon_api_v4.9.0.json:70851`, `embeddings/metadata.json:16660`) | The pattern index serves `project.Texts.GetGenre(text)` as the example for reading a text's genre. An assistant asking "what genre is this text" is taught the first-genre-only read. | **Medium** -- not a code defect in this repo, but it is the same bug class delivered as advice | Generated from Flexicon's `GetGenre` docstring. The durable fix is upstream: the `GetGenre` docstring should point at `GetGenres` in its See Also, then a refresh regenerates the index. File on `MattGyverLee/flexicon`. |
| `server/worked_examples.py:84` | `PhonemeSetsOS[0]` | Low | Intentional: an example adding a phoneme to the first phoneme set. Almost every project has exactly one. Not the FR-006 shape (the count is not what matters). |
| `server/worked_examples.py:219,223`, `curated_recipes.py:105,264,327`, `casting_helpers.py:17` | `entries[0]`, `senses[0]` in example/recipe code | Low | Tutorial code that deliberately takes "an entry" / "a sense" for illustration. Not a selection by value. |
| `server/handlers/parse.py:555` | `handle.results[0]` | None | Single-word request; exactly one result by construction. |
| `server/handlers/parse.py:788`, `server/parse/resolver.py:327` | `rows[0]` | None | Both guarded by an explicit `len(rows)` check; the multi-row case is handled (ambiguity). |

**Verdict**: no code sibling in `src/flextoolsmcp/`. One advice-level sibling in
the served pattern index, whose fix belongs upstream in Flexicon.

---

## Implementation finding (US1): writing systems on IndonesianHC-Complete

Live read-only smoke of `resolve_scope` on 2026-09-22, following the
vernacular-WS finding in [`live-note-fr001-fr003.md`](./live-note-fr001-fr003.md):

| Scope | `vernacular_ws` | Words | Unreadable (skipped) |
|---|---|---|---|
| all_texts | default (`id-fonipa`) | 38 IPA forms | 38 |
| all_texts | `id` | 38 orthographic forms | 38 |

The two texts hold **distinct** wordform objects -- 76 in all -- each stored in
one writing system only. Every run therefore skips exactly the other text's 38,
records the count in `unreadable_wordform_count`, and says in `notes` how to
reach them (`vernacular_ws`). It never emits `""` as a word. That is the
behaviour the live note asked for. The fingerprint records `vernacular_ws`, so
the two runs refuse to compare, and that refusal is correct.

**Not coverable live on this project**: neither text carries a genre (the
genres list is `[]` for both), so the two-genre case (SC-001) is covered only by
the offline fixture. T122 needs a project, or a text, that has more than one
genre.

---

## T052 -- name-sorted directory retention (R-03 shape)

**Date**: 2026-09-22 · **Scope**: `src/flextoolsmcp/`

**The shape**: choosing what to keep or delete by sorting names that are not
ordered the way the sort assumes. The anchor is `server/backup.py:50`
(`_prune_old_backups`), which sorts directory names and is sound only because
backup directories are UTC-timestamp-named. Run directories are
`token_hex(16)`, so the same mechanism would prune in random order.

**The fix at the anchor**: `server/parse/retention.py` orders by `meta.json`'s
`created_at`, keeps undatable runs out of the ordering (never deleted), and
protects live runs. Pinned by `tests/test_parse_retention.py`, whose fixture
reverses BOTH name order and mtime order against creation order, so a
name-sorted or `list_run_ids()`-ordered pruner fails.

**Method**: grep for `sorted(`/`.sort(` over `iterdir`/`listdir`/`glob`,
`key=lambda p: p.name`, `rmtree`/`unlink`/`os.remove`, `prune`/`retention`/
`rotate`, and `sorted(...)[-1]` "pick the latest" idioms; each hit read in
context.

### Siblings

| Location | What | Confidence | Disposition |
|---|---|---|---|
| `server/backup.py:50-67` | Name-sorted keep-newest-N over backup dirs | None (sound) | The anchor. Names ARE `%Y%m%dT%H%M%SZ` timestamps, so name order is time order, as its docstring says. Left as is. |
| `refresh.py:337-338` | `sorted(versions.keys())[-1]` picks the "latest" LibLCM index, with a comment claiming lexicographic order "works for semantic versioning" | **Medium** | Same bug class, different axis: version strings are not lexicographically ordered (`"8.10.0" < "8.9.0"`). Wrong the first time a LibLCM component reaches two digits. Not CP3's code; file an issue on `MattGyverLee/FlexToolsMCP`. `archive_old_versions.parse_version` already exists and is the fix. |
| `build_casting_index.py:242` | Same `sorted(versions.keys())[-1]` | **Medium** | As above. |
| `build_navigation_graph.py:367` | Same `sorted(versions.keys())[-1]` | **Medium** | As above. |
| `archive_old_versions.py:104` | Keeps latest by `parse_version` | None | Correct -- parses the version rather than sorting its string. The model for the three above. |
| `server/skeleton_storage.py:268,275` | Sorts entries by `captured_at` string | Low | Listing, not deletion; ISO-8601 strings in one timezone do sort chronologically. Not the shape. |
| `server/diagnostic/offered_store.py:126` | LRU prune by `last_seen` | None | Prunes by a recorded time, which is the right mechanism. |
| `server/handlers/op_telemetry.py:120` | Rotates `operations.jsonl` to `.1` by line count | None | Not an ordering decision. |
| `server/parse/record.py:152` (`list_run_ids`) | `st_mtime` order | None for its caller | Correct for naming the handles that exist (`parse_run_not_found`); explicitly NOT reused for retention, and a test asserts the two orders differ. |

**Verdict**: no retention sibling in code. One adjacent class -- lexicographic
sort of version strings to pick "latest" -- at three sites outside CP3; recorded
for an issue rather than fixed here, since none of them is on a CP3 path.
