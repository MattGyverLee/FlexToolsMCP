# flexicon coverage-gap triage

Indexes read:

- `lcm`: `src\flextoolsmcp\index\liblcm\liblcm_api_v11.0.0.json`
- `flexicon`: `src\flextoolsmcp\index\python\flexicon_api_v4.12.0.json`
- `bridge`: `src\flextoolsmcp\index\python\flexicon_lcm_bridge_v4.12.0.json`

## Structural picture

- 212 of 988 public LCM interfaces reachable (21.5%), covering 1248 of 3152 members (39.6%).
- **Member-level coverage is measured**: 273 members across 81 LCM types carry a type-resolved access recorded in the index.
- 114 candidate gaps carrying 415 members: in a served domain (lexicon, grammar, texts, wordform, notebook, discourse, reversal, core), declaring members, not a `*Tags` constant holder, not reachable by inheritance, and with ZERO measured member coverage.
- A further 338 unreachable interfaces sit outside those domains (scripture, system, service, general) and are not counted as gaps.
- Unreferenced is not the same as needed-and-missing. Only the log evidence below can tell you which of these anyone has actually reached for.
- flexicon: 125 classes, 1660 methods; 391 without an example, 116 of those mutating.

| LCM domain | interfaces | reachable | member surface | % surface reachable |
|---|---:|---:|---:|---:|
| general | 168 | 16 | 961 | 20.8 |
| grammar | 342 | 64 | 529 | 33.3 |
| scripture | 75 | 14 | 334 | 63.5 |
| system | 57 | 2 | 324 | 6.5 |
| core | 35 | 18 | 283 | 65.7 |
| lexicon | 60 | 27 | 274 | 79.6 |
| texts | 57 | 10 | 163 | 42.3 |
| wordform | 29 | 15 | 77 | 77.9 |
| factory | 59 | 23 | 67 | 47.8 |
| notebook | 12 | 2 | 45 | 82.2 |
| repository | 59 | 7 | 37 | 32.4 |
| reversal | 8 | 6 | 18 | 100.0 |
| service | 13 | 1 | 14 | 0.0 |
| discourse | 12 | 7 | 13 | 53.8 |
| writing_system | 2 | 0 | 13 | 0.0 |

## Live evidence

No log evidence supplied - this run is a structural audit only. Point `--logs` at a `~/.flextoolsmcp/logs` directory (or one a user sent you) to rank these gaps by what is actually being hit.
