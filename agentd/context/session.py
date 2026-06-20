import json
import time
import uuid
from typing import Any
from pathlib import Path
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# SessionStore -- 基于 JSONL 的会话持久化
# ---------------------------------------------------------------------------


class SessionStore:
    """管理 agent 会话的持久化存储。"""

    def __init__(self, base_dir: Path, agent_id: str = "default", user_name: str = "User"):
        self.agent_id = agent_id
        self.user_name = user_name
        self.base_dir = base_dir
        self.index_path = self.base_dir.parent / "sessions.json"
        self._index: dict[str, dict] = self._load_index()
        self.current_session_id: str | None = None
    
    def set_user_name(self, user_name: str):
        self.user_name = user_name
        self.base_dir = self._get_base_dir()
        self.index_path = self.base_dir.parent / "sessions.json"
        self._index = self._load_index()

    def _get_base_dir(self) -> Path:
        dir = self.base_dir / ".sessions" / "agents" / self.agent_id/ self.user_name / "sessions"
        dir.mkdir(parents=True, exist_ok=True)
        return dir
    
    def _load_index(self) -> dict[str, dict]:
        if self.index_path.exists():
            try:
                return json.loads(self.index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _session_path(self, session_id: str) -> Path:
        dir = self.base_dir
        return dir / f"{session_id}.jsonl"

    def create_session(self, label: str = "") -> str:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        self._index[session_id] = {
            "label": label,
            "created_at": now,
            "last_active": now,
            "message_count": 0,
        }
        self._save_index()
        self._session_path(session_id).touch()
        self.current_session_id = session_id
        return session_id

    def load_session(self, session_id: str) -> list[dict]:
        """从 JSONL 重建 API 格式的 messages[]。"""
        path = self._session_path(session_id)
        if not path.exists():
            return []
        self.current_session_id = session_id
        return self._rebuild_history(path)

    def save_turn(self, role: str, content: Any) -> None:
        if not self.current_session_id:
            return
        self.append_transcript(self.current_session_id, {
            "type": role,
            "content": content,
            "ts": time.time(),
        })

    def save_tool_result(self, tool_use_id: str, name: str,
                         tool_input: dict, result: str) -> None:
        if not self.current_session_id:
            return
        ts = time.time()
        # self.append_transcript(self.current_session_id, {
        #     "type": "tool_use",
        #     "tool_use_id": tool_use_id,
        #     "name": name,
        #     "input": tool_input,
        #     "ts": ts,
        # })
        self.append_transcript(self.current_session_id, {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": result,
            "ts": ts,
        })

    def append_transcript(self, session_id: str, record: dict) -> None:
        path = self._session_path(session_id)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        if session_id in self._index:
            self._index[session_id]["last_active"] = (
                datetime.now(timezone.utc).isoformat()
            )
            self._index[session_id]["message_count"] += 1
            self._save_index()

    def _rebuild_history(self, path: Path) -> list[dict]:
        """
        从 JSONL 行重建 API 格式的消息列表。

        Anthropic API 规则决定了这种重建方式:
          - 消息必须 user/assistant 交替
          - tool_use 块属于 assistant 消息
          - tool_result 块属于 user 消息
        """
        messages: list[dict] = []
        lines = path.read_text(encoding="utf-8").strip().split("\n")

        for line in lines:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            rtype = record.get("type")

            if rtype == "user":
                messages.append({
                    "role": "user",
                    "content": record["content"],
                })

            elif rtype == "assistant":
                content = record["content"]
                if isinstance(content, str):
                    content = [{"type": "text", "text": content}]
                messages.append({
                    "role": "assistant",
                    "content": content,
                })

            elif rtype == "tool_use":
                block = {
                    "type": "tool_use",
                    "id": record["tool_use_id"],
                    "name": record["name"],
                    "input": record["input"],
                }
                if messages and messages[-1]["role"] == "assistant":
                    content = messages[-1]["content"]
                    if isinstance(content, list):
                        content.append(block)
                    else:
                        messages[-1]["content"] = [
                            {"type": "text", "text": str(content)},
                            block,
                        ]
                else:
                    messages.append({
                        "role": "assistant",
                        "content": [block],
                    })

            elif rtype == "tool_result":
                result_block = {
                    "type": "tool_result",
                    "tool_use_id": record["tool_use_id"],
                    "content": record["content"],
                }
                # 将连续的 tool_result 合并到同一个 user 消息中
                if (messages and messages[-1]["role"] == "user"
                        and isinstance(messages[-1]["content"], list)
                        and messages[-1]["content"]
                        and isinstance(messages[-1]["content"][0], dict)
                        and messages[-1]["content"][0].get("type") == "tool_result"):
                    messages[-1]["content"].append(result_block)
                else:
                    messages.append({
                        "role": "user",
                        "content": [result_block],
                    })

        return messages

    def list_sessions(self) -> list[tuple[str, dict]]:
        items = list(self._index.items())
        items.sort(key=lambda x: x[1].get("last_active", ""), reverse=True)
        return items
    

