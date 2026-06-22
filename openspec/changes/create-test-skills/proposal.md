## Why

当前项目已有大量 skill（comet 系列、openspec 系列、superpowers 系列），但这些 skill 都是生产级别的复杂文档。当开发新功能或调试时，缺少轻量级测试 skill 来验证 Claude Code 的 skill 调用机制（Skill 工具、/slash 命令、自动匹配等）是否正常工作。

创建几个简单的测试 skill，方便在任何修改后快速验证 skill 系统功能。

## What Changes

- 创建 3 个轻量级测试 skill：
  1. **hello-skill**：最简单的 skill，仅输出问候语，验证基本 skill 调用
  2. **echo-args**：接收参数并回显，验证 skill 参数传递机制
  3. **system-info**：输出当前系统环境信息，验证 skill 可执行 shell 命令
- 每个 skill 仅包含一个 `SKILL.md` 文件，无额外依赖

## Capabilities

### New Capabilities
- `test-skills`: 轻量级测试 skill 集合，用于验证 Claude Code skill 调用机制

### Modified Capabilities

（无）

## Impact

- 仅新增 `workspace/skills/` 下的 3 个目录和文件
- 不影响任何现有代码或功能
- 不影响现有 skill 的行为
