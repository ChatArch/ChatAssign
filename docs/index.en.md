# ChatAssign Docs

ChatAssign is the ChatArch assignment control plane for connecting ChatEvent records, user confirmation, ChatBoard backends, and executor runs into an auditable task workflow.

Site entry: <https://arch.gh.wzhecnu.cn/ChatAssign/en/>

## Documentation Organization

- **CLI tree**: the current `chatassign` command tree, `serve` service entry, and verification commands.
- **Capability map**: ChatEvent consumer, confirmation gate, ChatBoard handoff, and safety boundaries.
- **Interface tree**: importable service, store, policy, and routing functions.

## Current Release Target

`0.1.0` promotes the verified VoiceNote assignment prototype into an installable package and local service:

- `chatassign serve` starts the HTTP API and static Web UI.
- Assignment state is written under a ChatArch-owned home.
- Voice Event records remain metadata-only by default; ChatAssign owns trigger policy and Zulip sender filtering.
- ChatBoard task/run side effects require the explicit confirmation gate.

## Local Preview

```bash
python -m pip install -e ".[dev,docs]"
python -m pytest -q
python tests/smoke_api.py
mkdocs serve
```
