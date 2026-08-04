# ADR-001: Python-native runtime with verifiable run integrity

- Status: Accepted
- Date: 2026-08-04
- Owners: pig-mono maintainers

## Context

pig-mono already has useful runtime behavior: provider/model selection, streaming
agent loops, tool execution, cancellation, steering and follow-up messages,
tree-backed sessions, semantic compaction, project trust, permission policies,
and a Python SDK wrapper.

Those capabilities are not yet governed by one durable execution authority. A
session can preserve conversation state, events can describe parts of an attempt,
and tool audit records can describe calls, but there is no canonical `Run` record
that proves which operations were accepted, which policy authorized them, which
artifacts they produced, and whether the run reached exactly one terminal outcome.
After a process interruption, the system cannot always distinguish a failed action
from an action whose external outcome is unknown.

At the same time, Python applications need to embed the runtime without inheriting
terminal-specific behavior or implicit authority from the coding-agent CLI.

## Decision

pig-mono will evolve toward a Python-native embeddable runtime whose defining
contract is verifiable run integrity.

The runtime will introduce explicit, durable identities and state transitions for:

- `Session`: conversational context and branch history.
- `Run`: one governed execution request and its terminal outcome.
- `Turn`: one model-facing reasoning cycle within a run.
- `Operation`: a provider call, tool call, policy decision, compaction, or other
  externally meaningful action.
- `Evidence`: append-only facts that support a transition or outcome.
- `Artifact`: content-addressed output produced or consumed by an operation.

The canonical terminal run outcomes will include `completed`, `failed`,
`cancelled`, and `outcome_unknown`. A run must reach at most one terminal outcome.
`outcome_unknown` is required when an external side effect may have happened but
cannot be proven after interruption or transport loss.

The first implementation will be incremental:

1. Define the run/event protocol and a local durable store inside the existing
   core runtime boundary.
2. Project current session, usage, retry, permission, and tool-audit behavior into
   that protocol without breaking the `0.2` APIs.
3. Add an async, transport-neutral host API after the authority model is stable.
4. Add external protocol adapters and multi-agent coordination only on top of the
   same run, policy, evidence, and lease contracts.

The coding-agent CLI, web UI, messenger integrations, and future transports are
hosts of the runtime. They may decide policy, presentation, and interaction, but
they may not invent run progress or terminal certainty that the runtime has not
recorded.

## Invariants

- Durable state transitions are append-only or transactionally derived from an
  append-only source of truth.
- A retried request retains a stable logical identity and records each attempt.
- Tool execution is preceded by an attributable policy decision.
- External side effects use idempotency keys when the target supports them.
- Process restart cannot silently convert an unfinished operation into success or
  failure.
- Evidence and artifact records are content-addressed where practical and redact
  credentials by construction.
- User-facing state is a projection of recorded runtime state, not an optimistic
  estimate.
- Host adapters fail closed when authority, policy, or trust is missing.

## Alternatives considered

### Continue feature breadth before adding run authority

This would deliver more tools and adapters quickly, but each new surface would add
another place where retries, permissions, partial side effects, and terminal state
could diverge. Rejected because it compounds migration and audit cost.

### Create a new runtime package and rewrite existing applications immediately

This could produce a clean namespace, but it would duplicate working behavior and
force a large cutover before the new protocol has conformance evidence. Rejected
for the first phase. Package extraction remains possible after the run protocol is
stable and both old and new host surfaces pass the same conformance suite.

### Keep events as observability only

Events without an authority model can explain activity but cannot prove which
state is canonical, whether a transition was accepted, or whether exactly one
terminal outcome exists. Rejected because observability alone is insufficient for
run integrity.

### Make the CLI the authoritative runtime

This would keep implementation concentrated, but terminal lifecycle, prompts, and
human confirmation are host concerns. Rejected because embedders, web transports,
and background workers need the same semantics without terminal coupling.

## Consequences

### Positive

- Python hosts gain a stable runtime boundary independent of terminal UI.
- Recovery, replay, audit, and user-visible status can share one source of truth.
- Protocol adapters and multi-agent workers can reuse the same leases, policies,
  evidence, and terminal outcomes.
- Tests can assert state-machine invariants instead of inferring correctness from
  output text.

### Costs and constraints

- Every side-effecting path must be mapped to a durable operation boundary.
- Existing session, usage, retry, permission, and audit stores will need adapters
  or migrations rather than parallel competing truth stores.
- Schema evolution and recovery semantics become compatibility commitments.
- A truthful `outcome_unknown` may be less satisfying than a guessed result, but it
  is required when evidence is incomplete.

## Follow-up

Implementation order, acceptance criteria, and explicit non-goals are maintained
in the [runtime roadmap](../roadmap.md).
