# config/logging_config.py
import logging

class ProjectFilter(logging.Filter):
    def filter(self, record):
        return record.name.startswith(("agentd", "cli", "gateway", "platforms", "utils"))

def setup_logging(level=logging.DEBUG):
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d %(levelname)s %(filename)s:%(lineno)d %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(ProjectFilter())

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)