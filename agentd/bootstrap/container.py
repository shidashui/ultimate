from config.configs import WORKSPACE_DIR
from agentd.bootstrap.loader import BootstrapLoader
from agentd.skill.skill import SkillsManager
from agentd.memory.memory import MemoryStore
from agentd.context.session import SessionStore
from agentd.context.context import ContextGuard
from agentd.tools.tool_handlers import TOOLS, TOOL_HANDLERS

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
        memory_store = MemoryStore(WORKSPACE_DIR)
        guard = ContextGuard()

        self.register("bootstrap_data", bootstrap_data)
        self.register("skills_mgr", skills_mgr)
        self.register("memory_store", memory_store)
        self.register("guard", guard)

        self.tools = TOOLS
        self.tools_handlers = TOOL_HANDLERS

# ✅ 全局唯一实例（但不是全局变量乱飞）
container = Container()