# Design: BaseProvider Abstraction

## Architecture Decision

### Interface

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

### Design Decisions

1. **Async-only** — sync 方法（`guard_api_call`、`message_client`）全部删除
2. **`**kwargs` 扩展** — 各 provider 自有参数（如 `max_tokens`、`temperature`）透传，不写在接口签名中
3. **方法名 `chat`** — 比 `create_message` 更直观
4. **参数序 `messages, system`** — system 通常可选，放后面
5. **路径 `agentd/providers/`** — 靠近使用方（ContextGuard、AgentRunner）
6. **新增 `estimate_tokens`** — 替代当前 ContextGuard 的字符数粗略估算
7. **v1 无流式** — `create_stream` 未使用，删除

## File Structure

```
新建:  agentd/providers/__init__.py     # get_provider() 工厂
新建:  agentd/providers/base.py         # BaseProvider + Response + ContentBlock
新建:  agentd/providers/anthropic.py    # AnthropicProvider

删除:  utils/clients.py                 # 逻辑移入 AnthropicProvider

修改:  agentd/context/context.py        # ContextGuard(provider) → 删同步方法
修改:  agentd/agent/runner.py           # AgentRunner(provider) → 序列化用新类型
修改:  config/configs.py                # get_provider() 工厂读取 config.json
修改:  agentd/bootstrap/container.py    # 启动时构造 provider 注入
修改:  cli/cli.py                       # 传递 provider
修改:  gateway/gateway.py               # 传递 provider
```

## Data Flow

```
config.json  →  get_provider(config)  →  BaseProvider 实例
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
              ContextGuard              AgentRunner               compact_history
              provider.chat()          provider.chat()           provider.chat()
```

## Risks

| Risk | Mitigation |
|------|-----------|
| Response 序列化断裂 | `Response` + `ContentBlock` 字段与当前 Anthropic ContentBlock 形状一致，`_serialize()` / `_extract_text()` 改为机械映射 |
| config.json 兼容 | 不改变 config.json 格式，仅开始读取已有 `provider` 字段 |
| 同步调用路径遗漏 | 全量搜索 `message_client` / `guard_api_call` 引用，确保全部替换 |
