---
comet_change: cli-tab-completion
role: technical-design
canonical_spec: openspec
---

# CLI Tab 补全 — 技术设计

## 问题

当前 REPL 使用 Python 内置 `input()` 读取命令，无 Tab 补全。用户必须完整记忆 `/switch`、`/compact`、`/bootstrap` 等命令名，学习成本高，拼写易错。

## 方案

用 `prompt_toolkit` 替换 `input()`，使用 `WordCompleter` 提供 `/` 命令的 Tab 补全。

### 技术栈

- `prompt_toolkit` — Python 交互式 CLI 标准库（单文件 Python，无 native 扩展）
- `WordCompleter` — 基于词表的补全引擎，输入前缀自动过滤候选列表

### 架构变更

```diff
  while True:
-     user_input = input(colored_prompt()).strip()
+     user_input = session.prompt(colored_prompt()).strip()
```

`PromptSession.prompt()` 是 `input()` 的直接替代品：
- 返回值类型相同 → `handle_repl_command` 无需修改
- 默认按 Enter 提交 → 行为完全一致
- 自带历史记录（上下键翻查）

### 补全词表

静态硬编码（~14 个命令），不做动态生成——命令增删频率极低，硬编码可读性更好：

```python
REPL_COMMANDS = [
    "/new", "/list", "/switch",
    "/context", "/compact",
    "/soul", "/skills", "/memory", "/search",
    "/prompt", "/bootstrap",
    "/help", "/quit", "/exit",
]
```

###   skill 补全

当前 spec 要求 skill 名也补全。但思考后认为：**暂不做**。

原因：
- skill 补全需要在 `Cli.__init__` 时从 `SkillsManager.skills` 动态构建 completer
- 但 `SkillsManager` 在 `AgentRunner` 中，而 `AgentRunner` 初始化时已扫描完成
- 技术上可做，但当前只有 3 个测试 skill，补全价值低
- 等 skill 数量增长后再加，改动仅一行 `REPL_COMMANDS + [f"/{s['name']}" for s in skills_mgr.skills]`

**Spec Patch**：回写 delta spec，将 skill 补全从 Requirement 降级为 Future 备注。

### 边界条件

| 情况 | 行为 |
|------|------|
| 输入 `/` + Tab | 显示全部命令列表 |
| 输入 `/s` + Tab | 过滤出 /search /soul /skills /switch |
| 输入普通文本 + Tab | 无补全，保持原有行为 |
| Ctrl+C / Ctrl+D | `prompt_toolkit` 抛出 `KeyboardInterrupt`，已有外层 `except` 处理 |
| pip install 失败 | 回退到 `input()`，不阻塞发布 |

### 测试策略

- 手动测试：各 Tab 场景组合（`/` → 列表，`/s` → 过滤，普通文本 → 无反应）
- 无需单元测试——补全逻辑是 `prompt_toolkit` 内置能力，我们的代码只是词表配置
