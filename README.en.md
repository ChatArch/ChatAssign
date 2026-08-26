<div align="center">
    <a href="https://pypi.python.org/pypi/ChatAssign">
        <img src="https://img.shields.io/pypi/v/ChatAssign.svg" alt="PyPI version" />
    </a>
    <a href="https://github.com/ChatArch/ChatAssign/actions/workflows/ci.yml">
        <img src="https://github.com/ChatArch/ChatAssign/actions/workflows/ci.yml/badge.svg" alt="Tests" />
    </a>
    <a href="https://arch.gh.wzhecnu.cn/ChatAssign/">
        <img src="https://img.shields.io/badge/docs-mkdocs-blue.svg" alt="Documentation" />
    </a>
</div>

<div align="center">

[English](README.en.md) | [简体中文](README.md)
</div>

# ChatAssign

ChatAssign is the ChatArch assignment control plane. It turns ChatEvent records into confirmation-gated assignment drafts, then routes confirmed work to a ChatBoard backend for Task/PRD creation and controlled executor runs.

Documentation entry: <https://arch.gh.wzhecnu.cn/ChatAssign/en/>

## Quick Start

```bash
pip install ChatAssign
chatassign --help
chatassign --version
chatassign --tree-brief
chatassign serve --host 127.0.0.1 --port 8765
```

## Current Capabilities

- Consume metadata-only ChatEvent voice records and open assignment drafts for `thought` / `sort` trigger aliases.
- Maintain a confirm-first assignment state machine; ChatBoard task/run side effects happen only after explicit confirmation.
- Consume Zulip reply events from an assignment topic while ChatAssign owns Rex/human and bot/self filtering.
- Create ChatBoard Task/PRD/run records through the ChatBoard HTTP backend, including mock, dry-run, and authorized real executor handoff.
- Persist assignment state, review, PRD, prompt, run references, and timeline under a ChatArch-owned home.

## Service Boundary

`chatassign serve` starts the local HTTP service. Long-lived credentials and runtime values belong in ChatEnv or process-owned runtime configuration. Public README/docs describe configuration categories only and must not include sensitive values.

## Development

```bash
python -m pip install -e ".[dev,docs]"
python -m pytest -q
python tests/smoke_api.py
mkdocs build --strict
python -m build
```

Read `AGENTS.md` and the docs capability/interface boundaries before extending the package.
