"""Tool call parameter validation and auto-repair.

Schema-driven type coercion + inspect-based default filling.
Pure function — no internal state, no side effects.
"""
from __future__ import annotations
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── type coercion ────────────────────────────────────────────

_SCHEMA_TYPE_TO_PYTHON: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _coerce(value: Any, target_type: str) -> tuple[Any, str | None]:
    """尝试将 value 强转为 target_type 对应的 Python 类型。

    Returns:
        (coerced_value, warning_or_none)
    """
    py_type = _SCHEMA_TYPE_TO_PYTHON.get(target_type)
    if py_type is None:
        return value, None  # unknown schema type, pass through

    # 已是对应类型 → 无需修复
    if isinstance(value, py_type):
        # 但 bool 是 int 的子类, 需要特殊处理
        if py_type is int and isinstance(value, bool):
            return int(value), f"coerced bool → int ({value!r} → {int(value)})"
        return value, None

    # bool("False") == True — 字符串 "False" 非空即 True, 这不符合直觉
    if py_type is bool and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True, f"coerced str → bool ({value!r} → True)"
        if lowered in ("false", "0", "no", ""):
            return False, f"coerced str → bool ({value!r} → False)"
        # fall through to abort below

    try:
        # int("5.0") 会失败, 先 float 再 int
        if py_type is int and isinstance(value, str):
            try:
                coerced = int(float(value))
            except (ValueError, TypeError):
                raise  # 重新抛出让外层 catch 处理
            return coerced, f"coerced str → int ({value!r} → {coerced})"
        coerced = py_type(value)
        return coerced, f"coerced {type(value).__name__} → {py_type.__name__} ({value!r} → {coerced!r})"
    except (ValueError, TypeError):
        return value, f"cannot coerce {value!r} to {target_type}"


# ── main entry ───────────────────────────────────────────────

def validate_and_repair(
    tool_input: dict[str, Any],
    schema: dict[str, dict] | None,
    handler: Callable | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """对 tool_input 进行校验和自动修复。

    Args:
        tool_input: LLM 生成的原始参数字典。
        schema: ToolRegistry 中的参数 schema（{name: {type, description}}）。
                为 None 时跳过修复（未知工具）。
        handler: 工具执行函数，用于提取默认值。为 None 时跳过默认值填充。

    Returns:
        (repaired_dict, warnings): warnings 为人类可读的修复/错误描述。
        修复失败时 returned dict 为空，warnings 包含错误信息。
    """
    if schema is None:
        return dict(tool_input), []

    repaired: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []

    # 提取 handler 默认值
    handler_defaults: dict[str, Any] = {}
    if handler is not None:
        try:
            sig = inspect.signature(handler)
            for pname, param in sig.parameters.items():
                if param.default is not inspect.Parameter.empty:
                    handler_defaults[pname] = param.default
        except (ValueError, TypeError):
            pass  # 无法 inspect 时跳过默认值填充

    # ── 1. 处理 tool_input 中存在的参数 ──
    for key, value in tool_input.items():
        if key not in schema:
            warnings.append(f"removed unknown param '{key}'")
            continue
        target_type = schema[key].get("type", "string")
        coerced, warn = _coerce(value, target_type)
        if warn and "cannot coerce" in warn:
            # coercion failure → hard error, repair impossible
            errors.append(f"param '{key}': {warn}")
            continue
        repaired[key] = coerced
        if warn:
            warnings.append(f"param '{key}': {warn}")

    # ── 2. 填充缺失参数 ──
    for key, info in schema.items():
        if key not in repaired:
            if key in handler_defaults:
                repaired[key] = handler_defaults[key]
                warnings.append(
                    f"param '{key}': filled default {handler_defaults[key]!r}"
                )
            elif handler is not None:
                # handler 存在但参数无默认值 → 必填参数缺失
                errors.append(f"missing required param '{key}'")

    # ── 3. 校验必填参数值非空 ──
    for key, info in schema.items():
        if key not in repaired:
            continue
        target_type = info.get("type", "string")
        if target_type == "string" and isinstance(repaired[key], str) and repaired[key] == "":
            # 只在 schema 中没有 default 且 handler 也没有 default 时报错
            if key not in handler_defaults:
                errors.append(f"param '{key}': empty string for required param")
                break

    if errors:
        return {}, errors

    return repaired, warnings
