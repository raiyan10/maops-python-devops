# Portfolio Guide

This document explains `maops-python-devops` to a technical reader —
client, recruiter, or interviewer — evaluating it as a portfolio piece.
It is deliberately technically grounded: what the project is, why it was
built this way, and what it demonstrates, without marketing language.

## The problem

DevOps and platform teams routinely need small, trustworthy diagnostic
tools: "what's my environment look like," "is this endpoint up," "what
does this log actually say happened," "did last night's checks all
pass." These tools are usually either shell scripts (fast to write, hard
to keep safe and typed as they grow) or heavyweight frameworks (safe, but
overkill for a diagnostics CLI). This project explores a third point: a
small, strictly typed, dependency-free Python CLI that treats its own
security boundaries — no shell, no arbitrary command execution, a
narrowly scoped network surface — as first-class design constraints from
day one, not retrofitted later.

`maops-python-devops` is Project 2 of a two-project portfolio pair.
Project 1, `maops-linux-devops-toolkit`, solves a related problem in
Bash. This project is an independent Python implementation sharing
portfolio house style (documentation conventions, CI structure, review
process) but no code or architecture — a deliberate choice to
demonstrate the same engineering discipline in a different language and
paradigm rather than port one implementation to another.

## Architecture

See [docs/architecture.md](architecture.md) for the complete diagrammed
system. In brief: an `argparse`-based CLI dispatches to one
`commands/*.py` orchestration function per subcommand, each of which
composes typed, frozen-dataclass models from `core/*.py`, then renders
them through one shared text/JSON/Markdown output layer
(`core/output.py`). Every command is read-only by default; the two
narrow, explicit exceptions (a fixed subprocess allowlist in
`core/runner.py`, a fixed network surface in `core/health_http.py`/
`core/health_tcp.py`) are each isolated to a single module and enforced
by dedicated architectural regression tests, not just code review.

## Feature evolution (why a seven-day arc)

The project was built as seven scoped daily increments, each ending in a
release-quality, tagged state rather than accumulating unreleased work:

1. **v0.1.0** — CLI skeleton, `doctor` environment checks, exit-code
   convention, CI matrix.
2. **v0.2.0** — Typed TOML configuration with full precedence resolution,
   and the safe subprocess runner (`core/runner.py`) later reused by
   `tools inspect`.
3. **v0.3.0** — `inventory system`/`inventory filesystem`, read-only
   host/OS/filesystem introspection with zero subprocess or network use.
4. **v0.4.0** — `logs parse`/`logs analyze`, a first-of-its-kind fd-safe
   log reader with bounded, sequential reads and default secret
   redaction.
5. **v0.5.0** — `health http`/`health tcp`, the package's first
   intentional network access, isolated to two modules with mandatory TLS
   verification and no insecure-mode flag.
6. **v0.6.0** — `report aggregate` and declarative `workflow` automation,
   composing every prior command's output/execution behind one
   normalization layer and one sequential, side-effect-scoped runner.
7. **v0.7.0** — Final hardening: closing deferred test-backstop and
   documentation-staleness findings from the Day 6 review, a final
   security audit, and the portfolio-facing documentation you are reading
   now.

Each day intentionally shipped a working, reviewed, tagged release rather
than a partial feature — a deliberate simulation of incremental,
release-driven delivery rather than a single large feature branch.

## Security model

Every security property in this project is enforced by an architectural
regression test, not only documented — see [SECURITY.md](../SECURITY.md)
for the complete boundary catalogue. The two properties most worth a
reviewer's attention:

- **The workflow file is data, not code.** `workflow run` parses a TOML
  file into typed dataclasses and dispatches a fixed, closed set of seven
  step kinds to the package's own existing report-building functions.
  There is no template engine, no `eval`, no shell interpolation — a
  shell-metacharacter-laden field is preserved as inert literal text and,
  at worst, produces a "path not found" failure. This is proven, not just
  asserted: `tests/unit/test_workflow_shell_metacharacter_inertness.py`
  feeds real `$(...)`/backtick/`;`/`|`/redirect/`${HOME}`/`&&` payloads
  through a real canary-file-creation attempt and asserts the file is
  never created.
- **The network surface is two files wide.** `core/health_http.py` and
  `core/health_tcp.py` are the only modules permitted to import
  `socket`/`ssl`/`http.client`; every other module's absence of network
  access is enforced by `tests/unit/test_no_network_health_boundary.py`
  performing a static import-boundary scan, not just a claim in a
  docstring.

## Testing strategy

The suite is split into `tests/unit/` (fast, fully isolated via
`monkeypatch` and dependency injection — no real host CPU count,
distribution, environment variables, or clock dependence) and
`tests/integration/` (real subprocess invocations of the installed CLI,
real loopback-only network I/O via ephemeral-port fixtures, never a
public host). Coverage is enforced at a 90% floor
(`--cov-fail-under=90`), currently held well above that floor, but
coverage percentage is treated as a floor, not a proof — the project's
own engineering-review history documents a case (see
[docs/engineering-reviews/day-06-test-review.md](engineering-reviews/day-06-test-review.md))
where two real defects sat on 99%-covered lines and were only caught by
pointing hostile input at the *specific* field that mattered, not by
coverage percentage. That review's own methodology — "read every line,
don't trust the percentage" — is itself a demonstrated practice in this
project, not just a stated intention.

## Release engineering

See [docs/release-process.md](release-process.md) for the complete,
accurate process. In short: branch → implement → `make quality` → `make
build` → `make smoke-install` → specialist review → blocker remediation
→ `make release-check` → pull request → Python 3.11-3.14 CI → merge →
`make release-check` on merged `main` → annotated tag → GitHub Release.
The one property worth calling out explicitly: `make smoke-install`
installs the **exact built wheel** (never editable source, never a fresh
PyPI resolve) into an isolated temporary venv with `PIP_NO_INDEX=1
--no-deps`, so a release is validated against the actual artifact a user
would receive, not a proxy for it.

## DevOps practices demonstrated

- Infrastructure-as-code discipline applied to a CLI tool: pinned CI
  action SHAs (never tags or branch names), a single-purpose CI workflow
  with `contents: read` and nothing more, deterministic build artifact
  normalization (`scripts/normalize_archive_permissions.py`) to remove
  filesystem-dependent noise from released archives.
- Security-as-architecture rather than security-as-checklist: every
  stated boundary (no shell, no arbitrary subprocess, scoped network,
  fd-safe file reads, atomic symlink-safe writes) has a corresponding
  automated regression test, several of them specifically architectural
  (static import scans, monkeypatched forbidden-call traps) rather than
  behavioral.
- Deterministic, dependency-free runtime: zero third-party runtime
  dependencies across all seven releases, reducing supply-chain surface
  to the Python standard library itself.
- A documented, followed review-and-remediation loop: specialist review
  documents under `docs/engineering-reviews/`, a stated Critical/High-
  blocks-release policy, and follow-up documents proving deferred
  Medium/Low findings were actually closed in a later pass rather than
  silently dropped.

## Representative usage

```bash
maops-py doctor --format json | python -m json.tool
maops-py inventory filesystem /var/log --max-depth 2 --top 10
maops-py logs analyze /var/log/app.log --format json
maops-py health http https://example.com/health --timeout 5
maops-py report aggregate doctor.json health.json --format markdown
maops-py workflow validate ci-checks.toml
maops-py workflow run ci-checks.toml --output run-report.json
```

See each command's own doc (`docs/inventory.md`, `docs/log-analysis.md`,
`docs/health-checks.md`, `docs/aggregated-reports.md`,
`docs/workflows.md`) for the complete flag reference — this list is
representative, not exhaustive, by design; the [README](../README.md)
takes the same approach.

## Design trade-offs

- **Standard-library-only over batteries-included.** Rejecting
  `click`/`typer`/`rich`/`pydantic` in favor of `argparse` and hand-
  written frozen dataclasses costs some ergonomics (more boilerplate per
  command) in exchange for zero supply-chain surface and full control
  over every serialization/validation code path. For a diagnostics tool
  whose trust model matters more than its development velocity, this
  trade favors the standard library.
- **Structural report-kind detection over heuristic guessing.** `report
  aggregate` requires a fixed, unique JSON key combination per supported
  report kind rather than a best-effort schema sniff — a document that
  doesn't structurally match any of the eight supported kinds is
  rejected outright, even if it "looks close." This costs flexibility
  (a slightly malformed real report is rejected, not repaired) in
  exchange for never impersonating a report kind it isn't.
- **A fixed, closed workflow step vocabulary over a general automation
  primitive.** `workflow run` deliberately has no templating, looping,
  conditionals, or plugin step kinds — every step is one of seven
  enumerated kinds, each a thin wrapper over an existing command. This
  trades expressiveness for the "declarative data, never executable
  code" property being a structural fact, not a policy.

## Intentionally excluded features

Documented explicitly (see [docs/roadmap.md](roadmap.md)'s "Optional
future enhancements" section) so their absence reads as a scoping
decision, not an oversight:

- No scheduler, cron integration, or daemon mode — `workflow run` is
  synchronous and run-once-per-invocation only.
- No plugin system or user-defined step kinds.
- No database, web UI, or persistent service component.
- No SSH, cloud-provider API integration, or credential management.
- No PyPI publishing workflow — releases are GitHub Releases only.
- No `--insecure`/TLS-bypass flag for `health http` — this is a safety
  invariant, not merely an unimplemented feature.
- No arbitrary command execution surface anywhere, at any layer.

This project's seven-day arc is complete as of v0.7.0; see
[docs/roadmap.md](roadmap.md) for the final status statement.
