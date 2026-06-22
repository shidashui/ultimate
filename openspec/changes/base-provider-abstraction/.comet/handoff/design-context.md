# Comet Design Handoff

- Change: base-provider-abstraction
- Phase: design
- Mode: compact
- Context hash: 0761c9da8ff1a8cd65685bb7f5ad21554f0b23830678a8563e26ada2943d31fb

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/base-provider-abstraction/proposal.md

- Source: openspec/changes/base-provider-abstraction/proposal.md
- Lines: 1-37
- SHA256: 682746e852c4a1d8c61c2fae25d6cd272a0a6fe26935065c1dd9377e88c6de39

```md
# Proposal: BaseProvider Abstraction

## Problem

The entire AI model API layer is hardcoded to the Anthropic Python SDK (`utils/clients.py`). Every component that makes LLM calls — `ContextGuard`, `AgentRunner`, and semantic compaction — directly or indirectly depends on `anthropic.Anthropic` / `anthropic.AsyncAnthropic` client instances and Anthropic-specific `ContentBlock` response types.

This means:
- **Cannot switch providers** — `config.json` has a `model.provider` field that is never read by code; swapping between DeepSeek, OpenAI, Ollama, etc. requires manually changing the `base_url` and hoping the Anthropic-compatible endpoint behaves identically.
- **Cannot support non-Anthropic API formats** — OpenAI's chat completions format, Ollama's API, and other providers use different request/response schemas that the current code cannot handle.
- **Tight coupling to SDK types** — `AgentRunner._serialize()` and `_extract_text()` iterate over `response.content` assuming Anthropic `ContentBlock` objects (`.type`, `.text`, `.id`, `.name`, `.input`).
- **No extension point** — adding a new provider requires modifying core agent loop code, not just adding a new file.

## Goal

Define a `BaseProvider` abstract base class that decouples the LLM API layer from the rest of the system, enabling:

1. Multiple API format support (Anthropic Messages, OpenAI Chat Completions, Ollama, etc.)
2. Provider selection driven by `config.json`
3. Clean extension via new provider implementations without touching core agent code

## Scope

### In Scope

- Define `BaseProvider` ABC with a normalized internal message format
- Implement `AnthropicProvider` wrapping the existing Anthropic SDK logic
- Refactor `utils/clients.py` into the provider module
- Update `ContextGuard` to accept a `BaseProvider` instance
- Update `AgentRunner` response serialization to use provider-normalized types
- Wire provider selection from `config.json`

### Out of Scope

- Implementing non-Anthropic providers (OpenAI, Ollama, etc.) — these become trivial after the abstraction exists but are separate work
- Changing the tool definition format (Anthropic/OpenAI tool schemas are already compatible)
- Streaming API refactor beyond what the abstraction needs
- Multi-provider fan-out or fallback logic
```

## openspec/changes/base-provider-abstraction/design.md

- Source: openspec/changes/base-provider-abstraction/design.md
- Lines: 1-75
- SHA256: f27173bfb6b2b5cd5410d6ff92e3f1572c631563b5f05f376897c22a9d7f4059

```md
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
```

## openspec/changes/base-provider-abstraction/tasks.md

- Source: openspec/changes/base-provider-abstraction/tasks.md
- Lines: 1-45
- SHA256: c40035f66ff5e0d6eb6172cae7673d5d77548f5f3aac916bc124b3d8d523d5fe

```md
# Tasks: BaseProvider Abstraction

## Task 1: Create BaseProvider ABC + normalized types

- [ ] Create `agentd/providers/__init__.py` with `get_provider()` factory
- [ ] Create `agentd/providers/base.py` with `BaseProvider` ABC, `Response`, `ContentBlock` dataclasses
- [ ] Commit

## Task 2: Implement AnthropicProvider

- [ ] Create `agentd/providers/anthropic.py` with `AnthropicProvider(BaseProvider)`
- [ ] Port `utils/clients.py` logic into `AnthropicProvider`
- [ ] Commit

## Task 3: Update ContextGuard to use BaseProvider

- [ ] Modify `agentd/context/context.py` — accept `BaseProvider` instance
- [ ] Replace `async_message_client()` calls with `provider.chat()`
- [ ] Remove sync methods (`guard_api_call`, `guard_api_call_stream`, `compact_history`)
- [ ] Commit

## Task 4: Update AgentRunner serialization

- [ ] Modify `agentd/agent/runner.py` — `_serialize()` and `_extract_text()` work with `Response` / `ContentBlock`
- [ ] Update `AgentRunner.__init__()` to accept/store provider
- [ ] Commit

## Task 5: Wire provider selection from config

- [ ] Update `config/configs.py` — `get_provider()` reads `config.json` model section
- [ ] Update `agentd/bootstrap/container.py` to instantiate provider at startup
- [ ] Delete `utils/clients.py`
- [ ] Commit

## Task 6: Update CLI/Gateway entry points

- [ ] Update `cli/cli.py` — pass provider to `AgentRunner`
- [ ] Update `gateway/gateway.py` — pass provider to `AgentRunner`
- [ ] Commit

## Task 7: Verify end-to-end

- [ ] Run existing tests
- [ ] Manual smoke test: REPL chat with AnthropicProvider
- [ ] Commit any fixes
```

## openspec/changes/base-provider-abstraction/specs/base-provider/spec.md

- Source: openspec/changes/base-provider-abstraction/specs/base-provider/spec.md
- Lines: 1-87
- SHA256: c54eee84f26e070e900668e9bdef3a79b8d5e77173d99e8f4ac2f3bd3380c753

[TRUNCATED]

```md
# BaseProvider Capability

## ADDED Requirements

### Requirement: BaseProvider Interface

The system SHALL provide a `BaseProvider` abstract base class in `agentd/providers/base.py` that defines the interface for all LLM API providers.

#### Scenario: Provider implements chat

**Given** a concrete provider inheriting from `BaseProvider`
**When** `chat(messages, system, tools, **kwargs)` is called
**Then** it SHALL return a `Response` with `content: list[ContentBlock]` and `stop_reason: str`

#### Scenario: Provider implements estimate_tokens

**Given** a concrete provider inheriting from `BaseProvider`
**When** `estimate_tokens(messages)` is called
**Then** it SHALL return an estimated token count as `int`

### Requirement: Normalized Response Types

The system SHALL define provider-agnostic dataclasses: `Response`, `ContentBlock`.

#### Scenario: ContentBlock for text

**Given** a provider response containing text
**When** the response is parsed
**Then** each text block SHALL have `type="text"` and a `text: str` field

#### Scenario: ContentBlock for tool use

**Given** a provider response containing a tool call
**When** the response is parsed
**Then** the tool block SHALL have `type="tool_use"`, `id: str`, `name: str`, and `input: dict` fields

### Requirement: AnthropicProvider

The system SHALL provide an `AnthropicProvider` in `agentd/providers/anthropic.py` that wraps the `anthropic` SDK and conforms to the `BaseProvider` interface.

#### Scenario: AnthropicProvider returns normalized response

**Given** an `AnthropicProvider` configured with api_key, base_url, and model name
**When** `chat()` is called with messages and system prompt
**Then** the Anthropic SDK response SHALL be translated to `Response` with normalized `ContentBlock` objects

#### Scenario: AnthropicProvider preserves stop_reason

**Given** an `AnthropicProvider` making an API call
**When** the API returns `stop_reason: "end_turn"` or `stop_reason: "tool_use"`
**Then** the `Response.stop_reason` SHALL match exactly

### Requirement: Provider Factory

The system SHALL provide a `get_provider(config)` factory function in `agentd/providers/__init__.py` that returns the correct `BaseProvider` instance based on configuration.

#### Scenario: Factory selects AnthropicProvider

**Given** a config dict with `{"provider": "anthropic"}` or a config where the current Anthropic-compatible endpoint is detected
**When** `get_provider(config)` is called
**Then** it SHALL return an `AnthropicProvider` instance

### Requirement: ContextGuard uses BaseProvider

The `ContextGuard` in `agentd/context/context.py` SHALL accept a `BaseProvider` instance and route all LLM API calls through it instead of calling `utils/clients.py` functions directly. Sync API methods SHALL be removed.

#### Scenario: ContextGuard calls provider

**Given** a `ContextGuard` initialized with a `BaseProvider` instance
**When** `async_guard_api_call()` is invoked
**Then** the provider's `chat()` method SHALL be called instead of the old `async_message_client()` function

### Requirement: AgentRunner uses normalized types

The `AgentRunner` in `agentd/agent/runner.py` SHALL work with `Response` and `ContentBlock` dataclasses instead of raw Anthropic SDK types.

#### Scenario: AgentRunner serializes Response

**Given** a `Response` returned by a provider
**When** `_serialize(response)` is called
```

Full source: openspec/changes/base-provider-abstraction/specs/base-provider/spec.md

