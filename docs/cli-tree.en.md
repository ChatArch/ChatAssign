# CLI Capability Map

`chatassign` is the command-line entry for the ChatAssign service. It currently exposes package verification and local HTTP service startup.

## Top-Level Commands

```text
chatassign                  # ChatAssign assignment control-plane CLI
├── --help                     # Show CLI help and registered commands
├── --version                  # Print the current package version
├── --tree                     # Print the registered CLI tree with parameter signatures
├── --tree-brief               # Print command nodes and descriptions without signatures
└── serve                      # Start the ChatAssign HTTP service
```

## Service Command

```text
chatassign serve --host 127.0.0.1 --port 8765
chatassign serve --home <chatarch-owned-home>
```

`serve` loads ChatAssign state, policy/backend configuration, HTTP APIs, and static Web assets. Credentials are supplied by ChatEnv or process-owned runtime configuration; public docs describe configuration categories and never include secret values.

## Verification Commands

```bash
chatassign --version
chatassign --tree-brief
chatassign serve --help
python tests/smoke_api.py
```

## Implementation Contract

- The CLI stays thin; substantive behavior is importable from `chatassign.server`.
- Any ChatBoard task/run side effect must pass the explicit confirmation gate.
- Real executor handoff requires backend-local executor permission; mock/dry-run remains available for safe demos.
