# Toolsmith

Read docs/specification.md before implementation. Toolsmith is a public,
MIT-licensed collection of optional generic libraries and CLI commands. It is not
a fleet runtime, evidence application, skills distribution or hosted platform.

WCBUBWHB: one current implementation, no compatibility aliases, hidden fallbacks,
dual storage paths or legacy interfaces. The CLI calls the library. Do not add
servers, listening sockets, daemons, unattended workers, helper processes,
subprocess execution or automatic installation/activation. Ordinary short-lived
CLI invocations are allowed. Browser automation and process-based PDF/OCR remain
excluded. Optional in-process MiniLM embeddings and vector retrieval are now
authorized. Keep one CPU-only, single-calling-thread implementation: no encoder
service, helper process, worker pool, automatic download or GPU/model fallback.
Do not add placeholder implementations.

Everything is optional to consumers. Core fleet setup, delivery, history and
lifecycle must never depend on Toolsmith. No skills, domain connectors, financial
calculations, taxonomies, prompts or agent definitions belong here. Do not modify
Bad Bets, GAAP or Crossfire consumers without a separate explicit instruction.

Use small functional modules, strict types without Any, typed expected results,
named public functions and validation at every public boundary. Keep modules
near 600 lines or less. Network and filesystem effects are explicit. Persist
only under explicitly selected private directories; no global defaults.
Configured scope prevents mistakes, not access by arbitrary same-user processes.
Never claim that metadata creates OS isolation.

Preserve credentials, shared work and production data. Verify backup/restore
before production changes; forward migrations only, never production resets.
Public source and built artifacts use the MIT license in LICENSE. This policy is
specific to Toolsmith; it does not relicense consumer projects. Keep private data,
credentials, model weights and local .analysis out of commits and artifacts.
Registry publication requires a separate explicit instruction. Owned npm packages,
if ever separately approved, use @ctlflow. Third-party rights remain intact.

Maintain docs/specification.md and .analysis/20261011-toolsmith/necessity-ledger.md.
Verify affected behavior, package contents and installed CLI/library parity.
Cross-layer changes require all quality gates. Never weaken a gate, use fixture
results as real-source certification or run unconditional test sleeps.
Do not add GitHub Actions CI/CD workflows. Verification and release checks run
locally through the existing scripts; hosted automation is not authorized.
Verification runs in an aggregate-memory/swap/task-bounded process group; no
unbounded test fallback. Development verification may launch ordinary compiler,
test and packaging commands, never product helper processes or test servers.

Never commit/push main, force-push, reset/clean/stash shared work or create PRs.
When authorized, commit/push a non-main branch and supply a manual
/pull/new/<branch> link. Git identity: jeswin <jeswinpk@agilehead.com>.
Do not delegate without a new explicit instruction. Status requests never pause
authorized work. Deployment requires a separate explicit instruction; installing
this package must not start any runtime or fleet.
