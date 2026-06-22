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
**Then** it SHALL return a list of dicts with `type`, `text`, `id`, `name`, `input` keys matching the ContentBlock fields

#### Scenario: AgentRunner extracts text from Response

**Given** a `Response` with mixed text and tool_use blocks
**When** `_extract_text(response)` is called
**Then** it SHALL return the concatenated text from all `type="text"` blocks
