# 能力地图

这个页面校对 `ChatAssign` 当前拥有的一等能力、已验证边界和仍然不属于当前包的范围。

## 能力分组

<div class="grid cards" markdown>

- **Assignment Control Plane**

    从 ChatEvent 事件创建 assignment 草案，维护 policy/review/confirmation/routing/run/timeline 状态。

- **HTTP Service / Web**

    `chatassign serve` 暴露 assignment API、contracts API、integrations API 和静态 Web UI。

- **ChatBoard Handoff**

    确认后调用 ChatBoard backend 创建 Task/PRD/run，并保留 public links 与 backend run reference。

</div>

## 当前边界

| 能力 | 状态 | 说明 |
| --- | --- | --- |
| CLI 基础入口 | 已实现 | `--version`、`--tree`、`--tree-brief`、`serve`。 |
| ChatEnv 配置提供者 | 已实现 | 配置类别覆盖 service、event、board、user-channel、resolver 和敏感 token 类别。 |
| Voice trigger policy | 已实现 | `source=voice` 且 tags 命中 `thought` / `sort` alias 时创建草案。 |
| Zulip reply policy | 已实现 | ChatAssign 过滤 Rex/human 与 bot/self；ChatEvent 只负责 topic-scope capture。 |
| Confirmation gate | 已验证 | 只有明确确认文本才触发 ChatBoard side effect，普通 clarification 不会误派发。 |
| ChatBoard HTTP handoff | 已验证 | 支持 Task/PRD/run link contract；real executor handoff 需要 backend executor permission。 |

## 不在当前范围

- 不把 voice transcript 默认写入 assignment/event 报告。
- 不由 ChatAssign 直接拥有低层 executor process；低层执行属于 ChatBoard backend。
- 不在 README、docs、issue、PR 评论或 CI log 中输出敏感值或授权头内容。
