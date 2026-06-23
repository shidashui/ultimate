from config.configs import WORKSPACE_DIR, get_model_provider, get_config
from agentd.bootstrap.loader import BootstrapLoader
from agentd.skill.skill import SkillsManager
from agentd.memory.memory import MemoryStore
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.tools.tool_handlers import get_tools, get_tool_handlers

class Container:
    def __init__(self):
        self.tools = []
        self.tools_handlers = {}
        self.services = {}

        self.initialize()

    def register(self, name, instance):
        self.services[name] = instance

    def get(self, name):
        return self.services[name]

    def initialize(self):
        # 这里可以添加一些全局初始化的逻辑，比如加载工具、设置环境变量等
        loader = BootstrapLoader(WORKSPACE_DIR)
        bootstrap_data = loader.load_all(mode="full")
        skills_mgr = SkillsManager(WORKSPACE_DIR)
        skills_mgr.discover()
        memory_store = MemoryStore(WORKSPACE_DIR)
        # SessionDB — FTS5 全文搜索对话历史
        from agentd.session.session_db import SessionDB
        session_db_path = WORKSPACE_DIR / ".sessions" / "sessions.db"
        session_db_path.parent.mkdir(parents=True, exist_ok=True)
        session_db = SessionDB(session_db_path)
        memory_store.session_db = session_db
        # Provider — 由 config.yaml 驱动，主备模式
        from agentd.providers import get_all_providers
        from agentd.providers.router import ProviderRouter
        all_providers = get_all_providers(get_config())
        provider_router = ProviderRouter(all_providers)
        guard = ContextGuard(provider_router=provider_router)

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("session_db", session_db)
        self.register("guard", guard)
        self.register("provider_router", provider_router)

        self.tools = get_tools()
        self.tools_handlers = get_tool_handlers()

# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()