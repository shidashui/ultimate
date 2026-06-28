# Design: Strip Markdown Before TTS

## Problem

`EdgeTTS.synthesize()` 直接将原始文本传给 `edge_tts.Communicate`，不做任何预处理。LLM 输出通常是 markdown 格式，朗读体验差。

## Solution

在 `synthesize()` 方法内，将 text 传给 edge_tts 之前做轻量 markdown→纯文本转换：

- 去掉标题前缀 `###` `##` `#`
- 去掉粗体/斜体标记 `**` `*` `__` `_`
- 去掉链接语法 `[text](url)` → 保留 text
- 去掉图片语法 `![alt](url)`
- 去掉行内代码 `` `code` ``
- 去掉代码块 ` ``` ` 围栏
- 去掉水平线 `---` `***`
- 去掉块引用 `>`
- 去掉无序列表前缀 `- ` `* ` `+ `
- 压缩多余空行

纯字符串处理，零新增依赖。

## 调用位置

```python
# platforms/voice/tts.py line 41
# Before:
communicate = Communicate(text, self.voice)
# After:
communicate = Communicate(self._strip_markdown(text), self.voice)
```
