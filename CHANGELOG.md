# Changelog

All notable changes to pig-mono are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-04

### Added

- Provider/model runtime ownership for provider registration, credential
  resolution, model metadata, capability filtering, catalog persistence, and
  explicit refresh.
- Model-gated deferred tools, strict JSON schemas, and grammar constraints.
- Branch-local semantic compaction with durable checkpoints, exact recent-tail
  preservation, provider-usage categorization, and rollback on summarization or
  atomic-save failure.
- Structured `TurnOutcome` results across provider, core runtime, CLI, RPC, JSON,
  and Python SDK boundaries.
- `ActiveTurnLifecycle` coordination for interactive turns, cancellation, and
  concurrent lifecycle transitions.
- A stable `create_agent_session()` embedding surface with structured permission
  denials.
- Repository release verification for tag/package/import/dependency consistency
  and exact PyPI artifact digests.
- Architecture decision and staged roadmap for a Python-native embeddable runtime
  with verifiable run integrity.

### Changed

- Aligned all six public packages at version `0.2.0` and raised local dependency
  floors to the same source-compatible baseline.
- Split coding-agent interaction dispatch, commands, flows, views, and terminal
  lifecycle into focused application/runtime modules.
- Made project-local configuration, instructions, prompts, skills, package roots,
  and extensions conditional on a canonical workspace trust decision.
- Made unattended, non-TTY, piped, JSON, RPC, generation, analysis, and default SDK
  routes fail closed for side-effectful tools.
- Made profile rotation rebuild the provider client with the selected credential
  before reporting the strategy transition.
- Strengthened strict typing across production code, tests, and examples, including
  Linux, macOS, and Windows CI coverage.
- Sequenced release publication so GitHub Releases are created only after PyPI
  publication and digest verification succeed.

### Fixed

- Preserved canonical tool calls, tool-call IDs, and activation anchors across
  session save/load and compaction.
- Prevented retries after a stream has already emitted partial output.
- Prevented permission prompts from crashing when stdin is closed or non-interactive.
- Corrected version drift between package manifests, import-time `__version__`
  values, dependency floors, and public documentation.

### Security

- Workspace trust discovery no longer requires reading untrusted project content.
- Side-effect authorization is explicit at each host boundary; unattended hosts do
  not inherit interactive approval behavior.
- Provider credential transitions use one-way profile fingerprints rather than raw
  keys or key prefixes in lifecycle events.

## [0.1.1] - 2026-06-08

### Changed

- Aligned `pig-llm` and `pig-tui` on the `0.1.1` package line.

### Release note

- The GitHub release was created, but PyPI deployment was rejected by the GitHub
  environment policy. The `0.2.0` pipeline makes registry publication and artifact
  verification prerequisites for the GitHub Release.

## [0.1.0] - 2026-06-05

### Added

- Initial `0.1` package line for the LLM, agent-core, terminal, and coding-agent
  surfaces.

### Release note

- The GitHub release was created, but the PyPI deployment job did not complete.

## 0.0.4 - 2026-03-04

### Added

- Profile-based retry and fallback primitives.
- Structured agent events, billing hooks, tool audit records, and usage tracking.
- Context compression and pluggable memory protocols.
- Coding-agent resilience and cost-reporting commands.

## 0.0.1 - 2026-02-23

### Added

- Initial monorepo package structure, provider adapters, agent/session/tool
  primitives, terminal and web surfaces, and messaging adapters.

[Unreleased]: https://github.com/kangkona/pig-mono/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/kangkona/pig-mono/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/kangkona/pig-mono/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/kangkona/pig-mono/releases/tag/v0.1.0
