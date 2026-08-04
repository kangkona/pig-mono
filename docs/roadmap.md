# Runtime roadmap

## Direction

pig-mono is building a Python-native embeddable agent runtime with verifiable run
integrity. The goal is not a larger feature checklist. The goal is a runtime whose
accepted work, authority, effects, recovery state, and terminal outcome can be
verified from durable evidence.

The architectural decision is recorded in
[ADR-001](decisions/ADR-001-python-runtime-and-run-integrity.md).

## Baseline: release 0.2.0

The `0.2.0` baseline contains:

- provider/model runtime ownership and capability metadata;
- sync and async agent loops with streaming, tool calls, cancellation, steering,
  follow-ups, and structured turn outcomes;
- tree-backed sessions and branch-local semantic compaction checkpoints;
- explicit project trust and fail-closed side-effect permission policies;
- an embeddable synchronous coding-agent session API;
- usage, retry, event, and tool-audit records;
- reusable terminal interaction primitives and application adapters;
- strict repository typing and multi-platform CI;
- tag/package/import/dependency verification plus exact PyPI artifact verification.

These are current code and release contracts. They are foundations for run
integrity, not proof that run integrity is already complete.

## Product and engineering principles

1. **One authority per fact.** Session history, run state, policy, usage, and
   artifacts may have projections, but each fact has one canonical owner.
2. **Evidence before certainty.** If an external result cannot be proven, record
   `outcome_unknown`; do not guess success or failure.
3. **Host policy is explicit.** CLI, SDK, web, messenger, and future transports
   supply trust and authorization decisions through typed interfaces.
4. **Fail closed at boundaries.** Missing policy, expired leases, unknown schema
   versions, and incomplete recovery evidence stop side effects.
5. **Stable identity across retries.** Logical runs and operations retain stable
   IDs while attempts remain separately observable.
6. **Backwards-compatible extraction.** Existing `0.2` APIs stay usable while
   runtime authority moves behind a more precise core interface.
7. **No invented progress.** User interfaces display recorded state and the next
   valid human action, not inferred percentages or ETAs.

## Target model

| Concept | Responsibility |
| --- | --- |
| `Session` | Conversation context, branches, and durable history |
| `Run` | One governed request, its lifecycle, and one terminal outcome |
| `Turn` | One model-facing reasoning cycle within a run |
| `Operation` | Provider, tool, policy, compaction, or artifact transition |
| `Attempt` | One retryable execution of an operation |
| `PolicyDecision` | Attributable allow, deny, or confirm result with scope |
| `Evidence` | Append-only fact supporting a transition or outcome |
| `Artifact` | Content-addressed input/output with provenance |
| `Lease` | Time-bounded authority to execute or recover owned work |

## Milestone R1: durable Run authority

Define the smallest durable execution protocol before adding more integrations.

Deliverables:

- Versioned IDs and schemas for `Run`, `Turn`, `Operation`, `Attempt`, and
  `Evidence`.
- An append-only event store with transactional projection updates. The first
  backend should be local and dependency-light; SQLite is the default candidate.
- A validated transition kernel for `pending`, `running`, `waiting`, and the
  terminal outcomes `completed`, `failed`, `cancelled`, and `outcome_unknown`.
- Stable idempotency keys for logical operations and explicit attempt numbers.
- Process-restart recovery that identifies expired ownership and never invents a
  terminal result.
- Adapters that project existing turn outcomes, retry lifecycles, usage records,
  compaction checkpoints, permission denials, and tool audits into the new model.

Exit criteria:

- Every run has zero or one terminal event; a second terminal transition is
  rejected deterministically.
- Replaying the event log yields the same run projection.
- Recovery tests cover interruption before dispatch, during provider streaming,
  before a tool side effect, after an unconfirmed side effect, and after durable
  completion.
- Existing CLI and SDK behavior passes unchanged through an adapter layer.

## Milestone R2: capability policy and evidence envelopes

Move from tool-name checks toward explicit, scoped authority while preserving the
current fail-closed host behavior.

Deliverables:

- Typed capabilities for filesystem reads/writes, process execution, network
  access, credential use, and host-provided tools.
- Policy decisions bound to run, operation, subject, target, scope, and expiry.
- Evidence envelopes that record request digests, decision provenance, result
  digests, redaction metadata, and external receipts.
- A tool broker interface that separates policy, dispatch, result validation, and
  durable commit.
- A sandbox adapter boundary. A concrete stronger-isolation backend is evaluated
  only after the boundary and conformance tests exist.

Exit criteria:

- No side-effecting operation can dispatch without a durable allow decision or a
  completed host confirmation.
- Expired, mismatched, or replayed grants fail closed.
- Credentials are referenced by opaque identity and never persisted in evidence.
- Tool results and produced artifacts can be correlated to the exact authorized
  operation.

## Milestone R3: async embeddable harness

Create the host-neutral runtime API after run and policy authority are stable.

Deliverables:

- `AsyncAgentSession`/`AgentHarness` interfaces for starting, observing,
  cancelling, steering, resuming, and closing runs.
- A typed event stream with ordering, backpressure, and resume cursors.
- Host callbacks for policy confirmation, trust, credentials, artifacts, and human
  attention.
- Transport adapters for the existing CLI, synchronous SDK wrapper, web UI, and
  messenger surfaces.
- Compatibility shims so the current synchronous embedding API remains usable.

Exit criteria:

- The same conformance scenario produces equivalent run/evidence projections
  through the CLI, sync SDK, async SDK, and one network transport.
- Cancellation and disconnect tests distinguish requested cancellation,
  confirmed cancellation, and unknown external outcome.
- Slow consumers cannot silently drop authoritative lifecycle events.

## Milestone R4: conformance, replay, and fault injection

Make runtime integrity continuously testable rather than a documentation claim.

Deliverables:

- A transport-neutral conformance suite for state transitions, policy decisions,
  event ordering, idempotency, and recovery.
- Deterministic fake providers and tools with injectable failures at every durable
  boundary.
- Read-only replay that rebuilds projections and explains the evidence behind a
  terminal outcome without re-executing side effects.
- Release evidence that records schema version, test suite result, built artifact
  digests, and package registry digests.

Exit criteria:

- Fault injection covers provider timeout, partial stream, tool timeout, process
  death, duplicate delivery, storage conflict, and recovery races.
- Replay is deterministic for every versioned fixture.
- A release fails before publication when protocol fixtures, projections, or
  artifact integrity disagree.

## Milestone R5: protocol adapters

Add interoperability after the core state and policy contracts are proven.

Deliverables:

- MCP client/server adapters mapped to typed capabilities and evidence records.
- ACP or equivalent agent-transport adapters mapped to run IDs, event cursors,
  cancellation, and terminal outcomes.
- Version and capability negotiation with explicit unsupported states.

Exit criteria:

- Protocol adapters cannot bypass the tool broker, policy kernel, or run ledger.
- Disconnect and retry behavior passes the same recovery and idempotency suite as
  local hosts.
- Protocol-specific envelopes remain adapters; they do not become a second source
  of runtime truth.

## Milestone R6: governed multi-agent and background work

Build coordination as relationships between governed runs, not as shared hidden
state.

Deliverables:

- Parent/child run links, scoped delegation grants, budgets, and durable leases.
- Background worker pickup, heartbeat, expiry, recovery, and attention queues.
- Typed handoff artifacts and explicit acceptance/rejection transitions.
- Aggregate projections for operators without weakening per-run evidence.

Exit criteria:

- A child cannot exceed the parent's delegated capability or budget.
- Lease expiry and worker loss result in deterministic recovery or
  `outcome_unknown`, never duplicate untracked execution.
- Parent completion cannot hide unresolved child runs or pending human attention.

## Sequencing and dependency rules

| Order | Why it comes next | What it must not pre-empt |
| --- | --- | --- |
| R1 | Establishes durable identity and state authority | New orchestration breadth |
| R2 | Binds side effects to explicit authority and evidence | Sandbox marketing without a tested boundary |
| R3 | Exposes the stable core to Python and transports | CLI-specific lifecycle leaking into the SDK |
| R4 | Proves recovery and integrity under faults | Feature claims based only on happy-path tests |
| R5 | Adds external protocols on the governed core | Protocol envelopes becoming runtime truth |
| R6 | Adds distributed coordination with leases and delegation | Shared mutable worker state without authority |

R4 fixtures begin during R1; the milestone is complete only when the suite is a
release gate. Security review is continuous, with a focused review at the R2 and
R5 boundaries.

## Explicit non-goals for the next milestone

- No multi-agent scheduler before durable single-run recovery exists.
- No new protocol adapter that can bypass the policy and evidence boundaries.
- No claim of process isolation until a concrete backend passes adversarial tests.
- No replacement of current public APIs solely to create a new package namespace.
- No progress percentage, delivery date, or reliability claim without measured,
  reproducible evidence.

## How roadmap status will be reported

Each milestone update must separate:

- **Implemented:** merged code and schema behavior.
- **Verified:** exact tests, fixtures, or external receipts proving the behavior.
- **Known gaps:** unsupported states and unverified assumptions.
- **Next gate:** the smallest acceptance criterion that unlocks the following work.

This roadmap is intentionally acceptance-criteria driven. Issue labels and project
boards may project the work, but they do not replace the runtime or release
evidence described here.
