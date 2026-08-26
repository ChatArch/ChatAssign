# Capability Map

Use this page to check the first-class capabilities `ChatAssign` owns, the verified boundaries, and what remains out of scope.

## Capability Groups

<div class="grid cards" markdown>

- **Assignment Control Plane**

    Create assignment drafts from ChatEvent records and maintain policy, review, confirmation, routing, run, and timeline state.

- **HTTP Service / Web**

    `chatassign serve` exposes assignment APIs, contracts APIs, integrations APIs, and static Web assets.

- **ChatBoard Handoff**

    After confirmation, call a ChatBoard backend to create Task/PRD/run records and retain public links plus backend run references.

</div>

## Current Boundary

| Capability | Status | Notes |
| --- | --- | --- |
| CLI base entry | Implemented | `--version`, `--tree`, `--tree-brief`, and `serve`. |
| ChatEnv provider | Implemented | Config categories cover service, event, board, user-channel, resolver, and sensitive token classes. |
| Voice trigger policy | Implemented | Drafts open for `source=voice` records whose tags match the `thought` / `sort` alias set. |
| Zulip reply policy | Implemented | ChatAssign filters Rex/human and bot/self identity; ChatEvent only captures the topic scope. |
| Confirmation gate | Verified | Only explicit approval text triggers ChatBoard side effects; ordinary clarification does not dispatch. |
| ChatBoard HTTP handoff | Verified | Supports Task/PRD/run link contracts; real executor handoff requires backend executor permission. |

## Out of Scope

- Do not write voice transcripts into assignment/event reports by default.
- Do not make ChatAssign own low-level executor processes; that belongs to the ChatBoard backend.
- Do not expose sensitive values or authorization header contents in README, docs, issues, PR comments, or CI logs.
