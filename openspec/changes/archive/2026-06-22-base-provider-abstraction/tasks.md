# Tasks: BaseProvider Abstraction

## Task 1: Create BaseProvider ABC + normalized types

- [x] Create `agentd/providers/__init__.py` with `get_provider()` factory
- [x] Create `agentd/providers/base.py` with `BaseProvider` ABC, `Response`, `ContentBlock` dataclasses
- [x] Commit

## Task 2: Implement AnthropicProvider

- [x] Create `agentd/providers/anthropic.py` with `AnthropicProvider(BaseProvider)`
- [x] Port `utils/clients.py` logic into `AnthropicProvider`
- [x] Commit

## Task 3: Update ContextGuard to use BaseProvider

- [x] Modify `agentd/context/context.py` — accept `BaseProvider` instance
- [x] Replace `async_message_client()` calls with `provider.chat()`
- [x] Remove sync methods (`guard_api_call`, `guard_api_call_stream`, `compact_history`)
- [x] Commit

## Task 4: Update AgentRunner serialization

- [x] Modify `agentd/agent/runner.py` — `_serialize()` and `_extract_text()` work with `Response` / `ContentBlock`
- [x] Update `AgentRunner.__init__()` to accept/store provider
- [x] Commit

## Task 5: Wire provider selection from config

- [x] Update `config/configs.py` — `get_provider()` reads `config.json` model section
- [x] Update `agentd/bootstrap/container.py` to instantiate provider at startup
- [x] Delete `utils/clients.py`
- [x] Commit

## Task 6: Update CLI/Gateway entry points

- [x] Update `cli/cli.py` — pass provider to `AgentRunner`
- [x] Update `gateway/gateway.py` — pass provider to `AgentRunner`
- [x] Commit

## Task 7: Verify end-to-end

- [x] Run existing tests
- [x] Manual smoke test: REPL chat with AnthropicProvider
- [x] Commit any fixes
