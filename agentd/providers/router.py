"""ProviderRouter — 管理多 provider 主备切换。

主备模式: providers[0] 为主，后续为备。
switch() 依次切换到下一个 provider，reset() 回到主。
"""
from agentd.providers.base import BaseProvider


class ProviderRouter:
    """按主备顺序管理多个 BaseProvider 实例。"""

    def __init__(self, providers: list[BaseProvider]):
        if not providers:
            raise ValueError("至少需要一个 provider")
        self._providers = providers
        self._idx = 0

    @property
    def current(self) -> BaseProvider:
        """返回当前活跃的 provider。"""
        return self._providers[self._idx]

    def switch(self) -> bool:
        """切换到下一个备选 provider。

        返回 True 表示切换成功，False 表示已无可切换 provider。
        """
        if self._idx + 1 < len(self._providers):
            self._idx += 1
            return True
        return False

    def reset(self) -> None:
        """回到主 provider（每 turn 开始时调用）。"""
        self._idx = 0
