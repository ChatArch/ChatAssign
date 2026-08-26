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

ChatAssign 是 ChatArch 的 assignment control-plane：它把 ChatEvent 事件转成需要确认的任务草案，经用户确认后路由到 ChatBoard 后端创建 Task/PRD 并启动受控 executor run。

文档入口：<https://arch.gh.wzhecnu.cn/ChatAssign/>

## 快速开始

```bash
pip install ChatAssign
chatassign --help
chatassign --version
chatassign --tree-brief
chatassign serve --host 127.0.0.1 --port 8765
```

## 当前能力

- 消费 metadata-only ChatEvent voice 事件，并按 `thought` / `sort` trigger alias 建立 assignment 草案。
- 维护确认优先的 assignment 状态机，只有明确确认后才创建 ChatBoard 任务或启动 run。
- 消费 assignment topic 内的 Zulip reply 事件，并由 ChatAssign 自己执行 Rex/human 与 bot/self 过滤。
- 通过 ChatBoard HTTP backend 创建 Task/PRD/run，并支持 mock、dry-run 或 backend 授权后的 real executor handoff。
- 将 assignment state、review、PRD、prompt、run reference 和 timeline 写入 ChatArch-owned home。

## 服务边界

`chatassign serve` 启动本地 HTTP service。长期凭据和值应放在 ChatEnv/运行环境中；公开 README 和 docs 只描述配置类别，不展示敏感值或连接串。

## 开发

```bash
python -m pip install -e ".[dev,docs]"
python -m pytest -q
python tests/smoke_api.py
mkdocs build --strict
python -m build
```

扩展前请阅读 `AGENTS.md` 和 docs 中的能力/接口边界。
