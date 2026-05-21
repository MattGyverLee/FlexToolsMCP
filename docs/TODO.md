# FlexToolsMCP — Project TODOs

Open questions and follow-up work, tracked in the repo so they survive between sessions.

---

## Re-evaluate: does `flextools_start_module` still earn its slot?

**Status:** open · **Added:** 2026-05-01

### The question

`flextools_start_module` is an interactive wizard that asks 5 required + 1 conditional + 1 optional question, then synthesizes a module template. Meanwhile `flextools_get_module_template` returns the same authoritative template directly, and `flextools_start`'s runtime primer already pushes the invariants the wizard is gesturing at. Is the wizard still pulling its weight, or is it ceremony the AI can route around with one `get_module_template` call?

### What to evaluate

- **Usage in real sessions.** How often is `start_module` actually called vs. `get_module_template`? If it's rarely called, that's signal.
- **Output divergence.** When `start_module` IS called, how does its generated template differ from what `get_module_template` would have returned plus a normal authoring step? Is there scaffolding only the wizard produces?
- **Conversational redundancy.** The wizard's questions (module_name, synopsis, api_target, modifies_db, domain) are almost always already answered in the user's request before the AI ever calls a tool. Asking them again may be friction, not safety.
- **Auto-injected guard overlap.** The wizard's headline safety feature is auto-injecting `if modifyAllowed:` on writes — but the runtime primer + gate 4 already enforce this independently. The wizard's contribution is making the guard *visible in the source* rather than enforced at validation. That has value, but it's not unique to the wizard if `get_module_template` produces the same scaffold.
- **Maintenance cost.** Two tools generating templates means two places to keep style-guide-aligned. Drift is a real risk.

### Possible outcomes

1. **Keep it** — usage data shows it adds value (e.g. when the AI doesn't know the user's intent yet, the structured Q&A surfaces requirements faster than free-form conversation).
2. **Fold it into `get_module_template`** — make the template tool accept the wizard's inputs as optional parameters and emit the same scaffold. One tool, no Q&A round-trip.
3. **Deprecate it** — runtime primer + `get_module_template` + gate 4 already cover the safety surface. Remove the wizard, keep the template.

### Next step

Pull operation logs and count `start_module` vs. `get_module_template` invocations across recent sessions. If the ratio is heavily skewed toward `get_module_template`, that's the answer — propose folding or deprecating in a follow-up plan doc.
