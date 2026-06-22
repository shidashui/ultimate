---
comet_change: base-provider-abstraction
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-22-base-provider-abstraction
status: final
---

# BaseProvider Abstraction — 技术设计

## 背景

整个 AI 模型 API 层硬编码在 Anthropic SDK（`utils/clients.py`）。`ContextGuard`、`AgentRunner`、语义压缩全部直接或间接依赖 `anthropic.Anthropic` / `anthropic.AsyncAnthropic` 实例和 Anthropic 专属的 `ContentBlock` 响应类型。`config.json` 中 `model.provider` 字段存在但从未被代码读取。

## 核心接口

```python
# agentd/providers/base.py

@dataclass
class ContentBlock:
    type: str           # "text" | "tool_use"
    text: str = ""      # type="text" 时有值
    id: str = ""        # type="tool_use" 时有值
    name: str = ""      # type="tool_use" 时有值
    input: dict = None  # type="tool_use" 时有值

@dataclass
class Response:
    content: list[ContentBlock]
    stop_reason: str    # "end_turn" | "tool_use" | "max_tokens"

class BaseProvider(ABC):
    @abstractmethod
    async def chat(self, messages, system, tools, **kwargs) -> Response: ...

    @abstractmethod
    def estimate_tokens(self, messages) -> int: ...
```

### 设计决策

| # | 决策 | 理由 |
|---|------|------|
| 1 | Async-only | 同步 `guard_api_call`、`message_client` 未被主循环使用，删除 |
| 2 | `**kwargs` 扩展 | 各 provider 自有参数（max_tokens、temperature）透传，不污染接口签名 |
| 3 | 方法名 `chat` | 比 `create_message` 直观 |
| 4 | 参数序 `messages, system` | system 通常可选，后置 |
| 5 | 路径 `agentd/providers/` | 靠近使用方 ContextGuard、AgentRunner |
| 6 | `estimate_tokens` | 替代当前 ContextGuard 字符数粗略估算 |
| 7 | v1 无流式 | `create_stream` / `guard_api_call_stream` 未被调用 |

## 文件变更

```text
新建:  agentd/providers/__init__.py
新建:  agentd/providers/base.py
新建:  agentd/providers/anthropic.py

删除:  utils/clients.py

修改:  agentd/context/context.py   — ContextGuard(provider), 删同步方法
修改:  agentd/agent/runner.py      — AgentRunner(provider), _serialize/_extract_text 适配
修改:  config/configs.py           — get_provider() 工厂
修改:  agentd/bootstrap/container.py — 启动时构造 provider
修改:  cli/cli.py                  — 传递 provider
修改:  gateway/gateway.py          — 传递 provider
```

## 数据流

```text
config.json  →  get_provider(config)  →  BaseProvider 实例
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              ContextGuard              AgentRunner               compact_history
              provider.chat()          provider.chat()           provider.chat()
```

## AnthropicProvider 实现要点

- 封装 `anthropic.AsyncAnthropic`，在 `__init__` 中按 config 创建
- `chat()` 调用 `messages.create()`，遍历 `response.content` 将 SDK 的 `ContentBlock` / `ToolUseBlock` / `TextBlock` 映射为归一化 `ContentBlock`
- `estimate_tokens()` 调用 `anthropic.count_tokens()`（若 SDK 版本支持），否则回退到字符数/4 估算
- `stop_reason` 直接透传

## 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| `_serialize/_extract_text` 断裂 | 低 | `Response`/`ContentBlock` 字段形状与当前 Anthropic 类型一致，机械映射 |
| config.json 兼容 | 低 | 不改变配置格式，仅开始读取已有字段 |
| 同步调用路径遗漏 | 中 | 全量搜索 `message_client`/`guard_api_call`/`guard_api_call_stream` 引用 |

## 测试策略

1. **AnthropicProvider 单元测试** — mock `anthropic.AsyncAnthropic`，验证请求参数完整透传 + 响应正确归一化（包括 text、tool_use、mixed 三种场景）
2. **ContextGuard 集成测试** — mock provider 注入，验证上下文溢出三级回退 + `estimate_tokens` 替换字符数估算
3. **回归** — REPL 启动 → 输入消息 → AI 正常回复（覆盖 chat → tool_use → end_turn 完整链路）
