## 设计决策

### 1. 配置格式：YAML

选用 YAML 而非 TOML/JSON 的理由：
- 注释支持（JSON 不支持，TOML 有限）
- Python 生态原生 `yaml` 库
- 可读性优于 JSON，层级比 TOML 直观
- `config.example.yaml` 可直接作为文档

### 2. 配置结构

```yaml
model:
  default: deepseek-v4-pro          # 当前使用的 provider
  providers:
    - name: deepseek
      base_url: https://api.deepseek.com/anthropic
      api_key_env: DEEPSEEK_API_KEY # 从环境变量读取，不写明文
    - name: openrouter
      base_url: https://openrouter.ai/api/v1
      api_key_env: OPENROUTER_API_KEY

toolsets:
  enabled: [memory, file, browser, skill]
  disabled: []

agent:
  max_iterations: 30
  context_safe_limit: 180000
```

### 3. Config 对象设计

`config/configs.py` 重构为配置加载器：

- `Config` dataclass 持有解析后的配置
- `load_config(path)` 函数：读取 YAML → 校验 → 返回 Config
- 模块级单例 `config = load_config("config.yaml")`
- 向后兼容：保留 `WORKDIR`、`WORKSPACE_DIR`、`BOOTSTRAP_FILES` 等路径常量

### 4. Provider 工厂适配

`get_provider()` 改为接收 Config 对象：
- 读取 `config.model.default` 找到当前 provider name
- 在 `config.model.providers` 列表中匹配 name
- 读取 `api_key_env` 环境变量获取 API key
- 后续新增 provider 只需在 `agentd/providers/` 添加实现 + YAML 配置

### 5. 迁移策略

- 删除 `config.json`
- 新增 `config.example.yaml`（不含 secrets，可提交 git）
- `config.yaml` 加入 `.gitignore`
- Python 硬编码常量（`CONTEXT_SAFE_LIMIT`、`MAX_TOOL_ITERATIONS`）迁移到 YAML

### 6. 风险

| 风险 | 缓解 |
|------|------|
| 现有 `config.json` 用户迁移 | `config.example.yaml` 提供模板；`config.yaml` gitignored |
| `yaml` 库可能未安装 | 在 `requirements.txt` 添加 `pyyaml` |
| 环境变量未设置导致启动失败 | `load_config()` 校验阶段给出明确错误信息 |
