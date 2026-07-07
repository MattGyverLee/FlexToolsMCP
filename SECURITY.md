# Security Policy

## Supported Versions

Only the latest published release receives security fixes.
Older versions are not patched; please upgrade.

| Version | Supported |
|---------|-----------|
| latest  | [YES]     |
| older   | [NO]      |

## Reporting a Vulnerability

Report security issues privately via **GitHub Security Advisories**:
https://github.com/MattGyverLee/FlexToolsMCP/security/advisories/new

You may also contact the maintainer directly at matthew_lee@sil.org.

Please include a description of the issue, steps to reproduce, and any
relevant version information. You will receive a response within 7 days.
Do not open a public GitHub issue for security vulnerabilities.

## Trust Model

**FlexToolsMCP is a localhost / stdio tool, not a network service.**

The MCP server is designed to be launched by a local AI assistant (Claude
Code, Copilot, etc.) over stdio and should never be exposed to a network
interface or an untrusted host. Exposing it to the network removes
protections the design relies on.

### Safety features (prevent accidental data damage)

- `write_enabled=False` by default: the server will not execute Create,
  Update, or Delete operations unless the caller explicitly opts in.
- Preflight validation checks generated scripts for unsafe patterns before
  execution.
- These controls protect against *mistakes* by the AI assistant or user.

### NOT security boundaries

`write_enabled` gating and preflight validation are **SAFETY** features,
not **SECURITY** boundaries. They are not designed to resist adversarial
input. Specifically:

- They do not prevent a malicious MCP client from setting `write_enabled=True`
  and issuing destructive commands.
- They do not sanitize AI-generated code for injection attacks.
- They do not authenticate or authorize callers.

If you run FlexToolsMCP in a context where the MCP client is not fully
trusted, you are operating outside the intended threat model. The tool
was built for a trusted local workflow: your AI assistant on your machine,
talking to your FieldWorks database.

### Prompt injection via lexicon data

Any party that controls the content of a `.fwdata` project -- a collaborator,
a downloaded wordlist, or a shared project -- can embed natural-language
instructions inside entry fields (headwords, glosses, definitions, notes, etc.)
that steer the AI into generating a destructive or exfiltrating script.
Because the runner is unsandboxed, that script executes with the full OS
privileges of the server process.  Setting `write_enabled=False` does NOT
neutralize this threat: a write-enabled invocation can still be triggered by
the MCP client after the AI has been influenced.  Treat every shared or
downloaded project as untrusted input, review AI-generated scripts before
running them, and prefer read-only mode when exploring unfamiliar databases.

### Subprocess execution

The server executes AI-generated Python code in a subprocess against the
user's live FieldWorks databases (`.fwdata` files). There is no sandbox.
Code that passes the preflight checks runs with the same OS privileges as
the server process. Do not grant the server elevated privileges.
