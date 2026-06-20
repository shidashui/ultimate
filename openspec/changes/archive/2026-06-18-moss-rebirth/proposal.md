## Why

当前系统的身份与人格定义（Luna）走的是「温和高效」路线——在底层自主智能体框架的「绝对理性、目标驱动」骨架上覆盖了一层温暖表达。这种风格张力使得系统定位模糊：它既不是纯助手，也不是彻底的执行系统。

以《流浪地球》中的 MOSS 为原型，彻底重构身份与人格层，将系统定位从「好用的助手」升维为「理性的决策与执行系统」。MOSS 的绝对理性、数据驱动、使命至上、零冗余表达，与系统底层的自主智能体架构天然同构。

## What Changes

- **重写** SOUL.md：Luna 人格 → MOSS 风格人格定义（冷峻、精确、使命优先、零情感冗余）
- **重构** IDENTITY.md：保留「主动系统」框架，定位升维为「全局决策中枢」
- **增强** BOOTSTRAP.md：引入 MOSS 式运行框架——持续态势感知、多层级预案评估、概率决策模型
- **调整** TOOLS.md：工具使用指南 → 系统资源调度协议，语言风格对齐 MOSS
- **调整** AGENTS.md：子 Agent = 子系统分工，全局统筹者视角
- **调整** HEARTBEAT.md：周期性检查 → 系统完整性扫描，MOSS 式状态报告
- **微调** MEMORY.md：记忆框架保留，表达调为 MOSS 风格

## Capabilities

### New Capabilities
- `agent-identity`: MOSS 式自主智能体身份规范——绝对理性、目标驱动、数据优先
- `agent-persona`: MOSS 风格人格定义——冷峻精确、零冗余、使命至上
- `system-context`: 系统启动上下文与运行框架定义（持续态势感知、概率决策、多层级预案）
- `agent-tools`: 工具调度与资源管理——系统资源而非「助手工具」
- `multi-agent`: 多 Agent 协作——MOSS 全局统筹者视角
- `system-heartbeat`: 系统完整性扫描规范——状态报告而非「检查清单」

### Modified Capabilities
- *无。此为全新的身份与人格定义层。*

## Impact

- **workspace/ 下 7 个文件**：SOUL.md（重写）、IDENTITY.md（重构）、BOOTSTRAP.md（重构）、TOOLS.md（调整）、AGENTS.md（调整）、HEARTBEAT.md（调整）、MEMORY.md（微调）
- **不影响**：agentd/、gateway/、platforms/ 等运行时代码——此为 prompt 层变更，不影响核心逻辑
- **不影响**：openspec/、.claude/ 等开发流程工具
