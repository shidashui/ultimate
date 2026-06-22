from config.configs import WORKSPACE_DIR, get_model_provider
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
        # Provider — 由 config.yaml 驱动
        provider = get_model_provider()
        guard = ContextGuard(provider=provider)

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("guard", guard)
        self.register("provider", provider)

        self.tools = get_tools()
        self.tools_handlers = get_tool_handlers()

# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()