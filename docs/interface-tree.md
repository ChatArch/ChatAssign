# Python 接口树

`ChatAssign` 的 CLI 保持薄入口；实质能力由 `chatassign.server` 提供，方便服务、测试和未来 adapter 复用。

## 包入口

```python
from chatassign import __version__
from chatassign.server import build_server, Store
```

## 服务入口

```text
chatassign
├── cli.py             # Click 入口；注册 --version/--tree/serve
├── config.py          # ChatEnv config provider
└── server.py          # HTTP service、state store、policy/review/router/run handoff
```

## 关键 API

```python
from chatassign.server import (
    Store,
    build_server,
    create_assignment,
    route_assignment,
    refine_from_reply,
    confirm_assignment,
    complete_assignment,
    voice_event_matches_policy,
    zulip_event_from_rex,
)
```

## 状态与安全边界

- `Store` 默认将 assignment、policy、backend、run 和 project artifacts 写入 ChatArch-owned home。
- `voice_event_matches_policy()` 只看 metadata/source/tags，不要求 voice transcript。
- `zulip_event_from_rex()` 属于 ChatAssign consumer policy，避免把 sender filtering 放进 ChatEvent capture 层。
- `confirm_assignment()` 是 ChatBoard task/run side effect 的入口；确认语义由 `is_confirmation_text()` 严格判断。
- `_dispatch_to_chatboard_http()` 通过 ChatBoard API handoff，低层 executor process 继续由 ChatBoard backend 拥有。
