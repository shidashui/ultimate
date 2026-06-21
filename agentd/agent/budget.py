class IterationBudget:
    """工具循环迭代预算，防止无限循环。"""

    def __init__(self, max_iterations: int = 30):
        self.max = max_iterations
        self.used = 0

    @property
    def remaining(self) -> int:
        return self.max - self.used

    def consume(self) -> bool:
        """消耗一次迭代。返回 True 表示还有剩余。"""
        self.used += 1
        return self.used <= self.max
