# Design: FormattedText 替代 ANSI

`colored_prompt()` 返回 `FormattedText([("ansicyan bold", "You > ")])`。

移除 `_ansi_render()` 和 `_ansi_console`（已无用）。
