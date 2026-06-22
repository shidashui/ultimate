## Why

SkillsManager 实例化后从未调用 `discover()`，导致 `workspace/skills/` 下的技能文件永远不会被扫描注入。即使技能文件存在，`format_skill_registry()` 始终返回 `"（无可用技能）"`，技能注入完全失效。

## What Changes

- 在 `container.py` 中 `SkillsManager` 实例化后追加 `skills_mgr.discover()` 调用

## Capabilities

### New Capabilities
- （无，纯 bug fix）

### Modified Capabilities
- （无行为变更，仅修复未调用的初始化步骤）

## Impact

- **1 个文件**：`agentd/bootstrap/container.py` +1 行
- SkillsManager 的 `discover()` 扫描逻辑本身已正确实现，只缺调用
