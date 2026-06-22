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
