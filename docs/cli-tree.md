# CLI 能力地图

`chatassign` 是 ChatAssign service 的命令行入口，当前提供基础包验证和本地 HTTP service 启动能力。

## 顶层命令

```text
chatassign                  # ChatAssign assignment control-plane CLI
├── --help                     # 显示 CLI 帮助和已注册命令
├── --version                  # 输出当前包版本
├── --tree                     # 输出真实已注册 CLI 树和参数签名
├── --tree-brief               # 输出命令节点和描述，不含参数签名
└── serve                      # 启动 ChatAssign HTTP service
```

## 服务命令

```text
chatassign serve --host 127.0.0.1 --port 8765
chatassign serve --home <chatarch-owned-home>
```

`serve` 会加载 ChatAssign 的状态目录、policy/backend 配置、HTTP API 和静态 Web assets。凭据由 ChatEnv 或进程运行环境提供；公开文档只描述配置类别，不展示 secret 值。

## 验证命令

```bash
chatassign --version
chatassign --tree-brief
chatassign serve --help
python tests/smoke_api.py
```

## 实现合约

- CLI 保持薄入口；实质能力在 `chatassign.server` 中可 import。
- 任何 ChatBoard task/run side effect 都必须经过明确 confirmation gate。
- Real executor handoff 需要 backend-local executor permission；默认演示仍可使用 mock/dry-run。
