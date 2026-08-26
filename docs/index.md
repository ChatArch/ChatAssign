# ChatAssign 文档

ChatAssign 是 ChatArch 的 assignment control-plane，用于把 ChatEvent 事件、用户确认、ChatBoard backend 和 executor run 串成可审计的任务流程。

站点入口：<https://arch.gh.wzhecnu.cn/ChatAssign/>

## 文档组织

- **CLI 能力地图**：当前 `chatassign` 命令树、`serve` 服务入口和验证命令。
- **能力地图**：ChatEvent consumer、confirmation gate、ChatBoard handoff 和安全边界。
- **Python 接口树**：可 import 的 service/store/policy 函数入口。

## 当前发布目标

`0.1.0` 将已验收的 VoiceNote assignment prototype 提升为可安装包和本地 service：

- `chatassign serve` 启动 HTTP API 和静态 Web UI。
- Assignment 状态写入 ChatArch-owned home。
- Voice Event 默认 metadata-only，ChatAssign 负责 trigger policy 与 Zulip sender filtering。
- ChatBoard task/run side effect 必须经过 explicit confirmation gate。

## 本地预览

```bash
python -m pip install -e ".[dev,docs]"
python -m pytest -q
python tests/smoke_api.py
mkdocs serve
```
