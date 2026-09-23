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
