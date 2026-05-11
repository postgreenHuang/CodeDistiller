"""
Code-Distiller AI 对话模块
- 每个对话关联一个代码项目
- Agent loop: AI 可以通过 [READ: path] 自主请求读取源文件
- 三层上下文管理: 压缩摘要 + 最近对话 + 按需读取
- session 持久化到 ~/.Code-Distiller/sessions/{session_id}/
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

_SESSIONS_DIR = Path.home() / ".Code-Distiller" / "sessions"
_FOLDERS_FILE = Path.home() / ".Code-Distiller" / "folders.json"

CHAT_SYSTEM_PROMPT = (
    "你是一位资深代码架构导师。你刚刚带领学生分析了一个代码工程。\n"
    "以下是工程的蒸馏笔记和关键源码片段，作为你的知识基础：\n\n"
    "--- 蒸馏笔记 ---\n{notes}\n\n"
    "--- 关键源码 ---\n{source}\n\n"
    "你的任务是：\n"
    "1. 回答关于代码架构、设计决策的问题\n"
    "2. 解释核心算法和数据结构的原理\n"
    "3. 帮助建立模块之间的关联理解\n"
    "4. 指出容易忽略的重要细节和潜在问题\n"
    "5. 建议深入阅读的方向\n\n"
    "--- 文件读取能力 ---\n"
    "当你需要查看项目源文件来准确回答问题时，你可以在回复中插入 [READ: 文件路径] 标记来请求读取文件。\n"
    "文件路径是相对于项目根目录的路径，如 src/gui/app.py。\n"
    "你可以同时请求多个文件，每个占一行。例如：\n"
    "[READ: src/core/engine.py]\n"
    "[READ: src/utils/helpers.py]\n"
    "系统会读取这些文件并将内容提供给你。读取到内容后，请基于实际代码给出准确回答。\n"
    "如果不确定文件路径，先根据项目结构推测最可能的路径。"
)

# Agent loop 常量
_READ_PATTERN = re.compile(r'\[READ:\s*([^\]]+)\]')
_MAX_READ_FILES = 5
_MAX_FILE_CHARS = 30000
_MAX_AGENT_ROUNDS = 4
_MAX_TOTAL_READ_CHARS = 120000

# 上下文预算常量
_DEFAULT_TOKEN_BUDGET = 60000      # 默认 token 预算
_COMPACT_THRESHOLD = 0.80          # 达到 80% 时触发压缩
_MIN_RECENT_MESSAGES = 6           # 压缩时至少保留最近 6 条消息
_MAX_MESSAGES = 80                 # messages 列表最大条数
_COMPACT_MAX_INPUT = 15000         # 压缩输入最大字符数
_COMPACT_PROMPT = (
    "请总结以下技术对话的关键信息（800字以内），保留：\n"
    "1. 讨论的主要话题和已得出的结论\n"
    "2. 已确认的代码架构理解\n"
    "3. 未解决的问题或疑问\n"
    "4. 关键文件和函数引用\n"
    "只输出总结内容，不要额外解释。"
)


def load_folders() -> list[dict]:
    if _FOLDERS_FILE.is_file():
        try:
            return json.loads(_FOLDERS_FILE.read_text(encoding="utf-8")).get("folders", [])
        except Exception:
            pass
    return []


def save_folders(folders: list[dict]):
    _FOLDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_FOLDERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"folders": folders}, f, ensure_ascii=False, indent=2)


class ChatSession:
    """管理单个对话 session，支持 agent loop + 自动上下文压缩"""

    def __init__(self, session_dir: str, provider_config: dict):
        self.session_dir = session_dir
        self.history_path = os.path.join(session_dir, "chat_history.json")
        self.provider = provider_config
        self.base_url = provider_config.get("base_url", "").rstrip("/")
        self.api_key = provider_config.get("api_key", "")
        self.model = provider_config.get("model", "")
        self.system_prompt = ""
        self.messages: list[dict] = []
        self.name = ""
        self.created_at = ""
        self.folder_id = ""
        self.notes_path = ""
        self.project_path = ""
        self._summary: str = ""  # 压缩摘要
        self._token_budget = _DEFAULT_TOKEN_BUDGET
        self._file_list_cache: str = ""  # 项目文件列表缓存

    def initialize(self, notes_path: str = "", project_path: str = "") -> bool:
        """加载蒸馏结果构建 system prompt"""
        notes = self._read_file(notes_path)
        source = self._collect_key_sources(project_path)

        if not notes and not source:
            return False

        self.system_prompt = CHAT_SYSTEM_PROMPT.format(
            notes=notes or "(未找到蒸馏笔记)",
            source=source or "(未找到源码)",
        )
        self._load_history()
        if notes_path:
            self.notes_path = notes_path
        if project_path:
            self.project_path = project_path
        if notes and not self.messages:
            self.messages.append({"role": "assistant", "content": notes})
        return True

    def update_files(self, notes_path: str = "", project_path: str = ""):
        self.notes_path = notes_path
        self.project_path = project_path
        notes = self._read_file(notes_path)
        source = self._collect_key_sources(project_path)
        if notes or source:
            self.system_prompt = CHAT_SYSTEM_PROMPT.format(
                notes=notes or "(未找到蒸馏笔记)",
                source=source or "(未找到源码)",
            )
        if notes and not self.messages:
            self.messages.append({"role": "assistant", "content": notes})
        if notes_path:
            self.name = Path(notes_path).stem
        self._save_history()

    # ─── 主对话入口 ───

    def chat(self, user_message: str, on_read_files=None, on_status=None) -> str:
        """Agent loop + 三层上下文管理"""
        if not self.system_prompt:
            return "请先运行蒸馏分析，然后再开始对话。"

        self.messages.append({"role": "user", "content": user_message})

        # 检查是否需要压缩上下文
        if self._needs_compaction():
            self._compact_messages()

        # Agent loop
        reply = ""
        extra_context = []
        total_read_chars = 0

        for round_num in range(_MAX_AGENT_ROUNDS):
            api_messages = self._build_budgeted_messages()
            api_messages.extend(extra_context)

            reply = self._call_provider(api_messages)

            read_paths = _READ_PATTERN.findall(reply)
            if not read_paths:
                break

            resolved = self._resolve_file_paths(read_paths[:_MAX_READ_FILES])
            if not resolved:
                # 文件找不到 → 给 AI 实际文件列表让它纠正路径
                extra_context.append({"role": "assistant", "content": reply})
                not_found = ", ".join(p.strip() for p in read_paths[:_MAX_READ_FILES])
                file_list = self._get_project_file_list()
                if file_list:
                    extra_context.append({
                        "role": "user",
                        "content": (f"无法找到请求的文件: {not_found}\n\n"
                                    f"以下是项目中实际存在的文件列表:\n"
                                    f"```\n{file_list}\n```\n\n"
                                    "请根据上面的文件列表使用正确路径重新请求读取 [READ: 正确路径]。\n"
                                    "如果仍找不到需要的文件，请基于已有信息回答。"),
                    })
                else:
                    extra_context.append({
                        "role": "user",
                        "content": (f"无法找到请求的文件: {not_found}\n"
                                    "项目路径未配置，无法列出文件。\n"
                                    "请在对话界面点击齿轮⚙按钮配置项目文件夹路径。\n"
                                    "现在请基于已有的上下文信息来回答问题。"),
                    })
                if on_status:
                    on_status("fallback")
                continue

            if on_read_files:
                on_read_files([r[0] for r in resolved])
            if on_status:
                on_status("analyzing")

            file_contents, read_chars = self._read_files_for_context(
                resolved, max_remaining=_MAX_TOTAL_READ_CHARS - total_read_chars
            )
            total_read_chars += read_chars

            if not file_contents:
                extra_context.append({"role": "assistant", "content": reply})
                extra_context.append({
                    "role": "user",
                    "content": "文件内容为空或读取失败。请基于已有的上下文信息来回答问题。",
                })
                continue

            extra_context.append({"role": "assistant", "content": reply})
            extra_context.append({"role": "user", "content": file_contents})

        reply = _READ_PATTERN.sub('', reply).strip()

        self.messages.append({"role": "assistant", "content": reply})
        self._save_history()
        return reply

    def clear_history(self):
        self.messages.clear()
        self._summary = ""
        self._save_history()

    # ─── Provider ───

    def _call_provider(self, messages: list[dict]) -> str:
        import requests

        if not self.base_url or not self.api_key:
            raise ValueError("请先在设置中配置 AI Provider 的 URL 和 API Key")

        url = self.base_url + "/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 8192,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=180)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    # ─── 三层上下文管理 ───

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """估算 token 数（中英混合：约每 3 字符 1 token）"""
        if not text:
            return 0
        return len(text) // 3

    def _total_messages_tokens(self) -> int:
        """计算所有消息的 token 总数"""
        return sum(self._estimate_tokens(m.get("content", "")) for m in self.messages)

    def _needs_compaction(self) -> bool:
        """检查是否需要压缩上下文"""
        total = self._estimate_tokens(self.system_prompt)
        if self._summary:
            total += self._estimate_tokens(self._summary)
        total += self._total_messages_tokens()
        return total > self._token_budget * _COMPACT_THRESHOLD

    def _compact_messages(self):
        """将旧消息压缩为摘要，保留首条（笔记）和最近消息"""
        # 至少需要 > MIN_RECENT + 1（首条笔记）才值得压缩
        if len(self.messages) <= _MIN_RECENT_MESSAGES + 1:
            return

        # 首条 assistant 消息（蒸馏笔记）不压缩
        first_msg = self.messages[0] if self.messages else None
        rest = self.messages[1:]

        if len(rest) <= _MIN_RECENT_MESSAGES:
            return

        split = len(rest) - _MIN_RECENT_MESSAGES
        old_messages = rest[:split]
        recent_messages = rest[split:]

        # 构建压缩输入：已有摘要 + 旧消息
        parts = []
        if self._summary:
            parts.append(f"[之前的对话摘要]\n{self._summary}")
        for m in old_messages:
            content = m.get("content", "")
            role = m.get("role", "user")
            # 每条消息截断到 500 字符避免输入太长
            parts.append(f"[{role}] {content[:500]}")

        conversation_text = "\n\n".join(parts)[:_COMPACT_MAX_INPUT]

        try:
            compact_messages = [
                {"role": "system", "content": _COMPACT_PROMPT},
                {"role": "user", "content": conversation_text},
            ]
            summary = self._call_provider(compact_messages)
            self._summary = summary

            # 摘要消息替换旧消息
            summary_msg = {
                "role": "assistant",
                "content": f"📝 [对话历史摘要]\n{summary}",
            }
            self.messages = [first_msg, summary_msg] + recent_messages if first_msg else [summary_msg] + recent_messages

            self._save_history()
        except Exception:
            # 压缩失败时，直接截断旧消息（不调 AI，零成本）
            if first_msg:
                self.messages = [first_msg] + self.messages[-_MIN_RECENT_MESSAGES:]
            else:
                self.messages = self.messages[-_MIN_RECENT_MESSAGES:]
            self._save_history()

    def _build_budgeted_messages(self) -> list[dict]:
        """构建 token 预算内的 API 消息列表

        三层结构：
        1. System prompt (蒸馏笔记 + 源码) — 始终保留
        2. Messages (从最新往回填充)
        3. Agent loop extra context 由调用者追加
        """
        messages = [{"role": "system", "content": self.system_prompt}]
        budget = self._token_budget - self._estimate_tokens(self.system_prompt)

        if budget <= 1000:
            return messages

        # 从最新消息往回填充
        selected = []
        for msg in reversed(self.messages):
            msg_tokens = self._estimate_tokens(msg.get("content", ""))
            if msg_tokens > budget:
                break
            selected.append(msg)
            budget -= msg_tokens

        selected.reverse()
        messages.extend(selected)
        return messages

    # ─── 文件读取 (Agent Loop) ───

    def _resolve_file_paths(self, raw_paths: list[str]) -> list[tuple[str, str]]:
        project = self.project_path
        if not project or not os.path.isdir(project):
            return []

        project_norm = os.path.normpath(project)
        resolved = []
        seen = set()

        for raw in raw_paths:
            path = raw.strip().strip('`\'" \t\n')
            if not path or path in seen:
                continue
            seen.add(path)

            full = os.path.normpath(os.path.join(project, path))
            if not full.startswith(project_norm + os.sep) and full != project_norm:
                continue
            if os.path.isfile(full):
                size_kb = os.path.getsize(full) / 1024
                if size_kb <= 512:
                    resolved.append((path, full))

        return resolved

    def _read_files_for_context(self, resolved_paths: list, max_remaining: int) -> tuple[str, int]:
        parts = []
        total_chars = 0

        for rel_path, full_path in resolved_paths:
            try:
                content = Path(full_path).read_text(encoding="utf-8", errors="ignore")
                if len(content) > _MAX_FILE_CHARS:
                    lines = content.splitlines()
                    content = "\n".join(lines[:200]) + "\n... (省略中间部分) ...\n" + "\n".join(lines[-50:])
                if total_chars + len(content) > max_remaining:
                    content = content[:max(0, max_remaining - total_chars)]
                    if content:
                        content += "\n... (已截断)"
                parts.append(f"### 文件: {rel_path}\n```\n{content}\n```")
                total_chars += len(content)
            except Exception:
                parts.append(f"### 文件: {rel_path}\n(读取失败)")

        if not parts:
            return "", 0

        header = f"以下是请求的 {len(parts)} 个文件的内容：\n\n"
        return header + "\n\n".join(parts), total_chars

    def _get_project_file_list(self) -> str:
        """获取项目文件列表（带缓存），用于帮助 AI 定位正确路径"""
        if self._file_list_cache:
            return self._file_list_cache
        if not self.project_path or not os.path.isdir(self.project_path):
            return ""
        from .scanner import _scan_file_tree, _flatten_files
        root = Path(self.project_path)
        tree = _scan_file_tree(root)
        files = _flatten_files(tree, str(root))
        self._file_list_cache = "\n".join(files[:300])
        return self._file_list_cache

    # ─── 持久化 ───

    def _save_history(self):
        os.makedirs(self.session_dir, exist_ok=True)
        data = {
            "name": self.name,
            "created_at": self.created_at,
            "folder_id": self.folder_id,
            "project_path": self.project_path,
            "notes_path": self.notes_path,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "summary": self._summary,
        }
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_history(self):
        if os.path.exists(self.history_path):
            try:
                data = json.loads(Path(self.history_path).read_text(encoding="utf-8"))
                self.messages = data.get("messages", [])
                self.name = data.get("name", self.name)
                self.created_at = data.get("created_at", "")
                self.folder_id = data.get("folder_id", "")
                self.project_path = data.get("project_path", "")
                self.notes_path = data.get("notes_path", "")
                self._summary = data.get("summary", "")
                if data.get("system_prompt"):
                    self.system_prompt = data["system_prompt"]
            except Exception:
                self.messages = []

        if self.notes_path and not self.messages:
            notes = self._read_file(self.notes_path)
            if notes:
                self.messages.append({"role": "assistant", "content": notes})

    # ─── 工具 ───

    @staticmethod
    def _read_file(path: str) -> str:
        if path and os.path.exists(path):
            try:
                return Path(path).read_text(encoding="utf-8").strip()
            except Exception:
                pass
        return ""

    @staticmethod
    def _collect_key_sources(project_path: str, max_files: int = 10) -> str:
        if not project_path or not os.path.isdir(project_path):
            return ""
        from .scanner import _detect_entry_files, _scan_file_tree, _flatten_files
        root = Path(project_path)
        tree = _scan_file_tree(root)
        all_files = _flatten_files(tree, str(root))
        entries = _detect_entry_files(root, all_files)

        parts = []
        for rel in entries[:max_files]:
            full = root / rel
            try:
                size_kb = full.stat().st_size / 1024
                if size_kb > 256:
                    continue
                content = full.read_text(encoding="utf-8", errors="ignore")
                if content:
                    parts.append(f"### {rel}\n```\n{content[:3000]}\n```")
            except Exception:
                continue
        return "\n\n".join(parts)


# ─── Session 管理 ───

def create_session(project_path: str, notes_path: str = "",
                   provider_config: Optional[dict] = None) -> ChatSession:
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")

    session_dir = os.path.join(str(_SESSIONS_DIR), ts)
    os.makedirs(session_dir, exist_ok=True)

    cfg = provider_config or {}
    session = ChatSession(session_dir, cfg)
    session.created_at = now.strftime("%Y-%m-%d %H:%M:%S")

    if not notes_path and project_path:
        notes_dir = os.path.join(project_path, "notes")
        if os.path.isdir(notes_dir):
            for f in sorted(os.listdir(notes_dir), reverse=True):
                if f.endswith(".md"):
                    notes_path = os.path.join(notes_dir, f)
                    break

    session.initialize(notes_path, project_path)

    if project_path:
        session.name = f"{Path(project_path).name} {now.strftime('%m-%d %H:%M')}"
    elif session.notes_path:
        session.name = Path(session.notes_path).stem
    else:
        session.name = now.strftime("%m-%d %H:%M")

    session._save_history()
    return session


def list_sessions(show_hidden: bool = False) -> list[dict]:
    results = []
    if not _SESSIONS_DIR.is_dir():
        return results

    for sid in sorted(os.listdir(_SESSIONS_DIR), reverse=True):
        sdir = str(_SESSIONS_DIR / sid)
        hfile = os.path.join(sdir, "chat_history.json")
        if not os.path.isfile(hfile):
            continue
        try:
            data = json.loads(Path(hfile).read_text(encoding="utf-8"))
        except Exception:
            continue

        hidden = data.get("hidden", False)
        if hidden and not show_hidden:
            continue

        msgs = data.get("messages", [])
        rounds = sum(1 for m in msgs if m.get("role") == "user")
        results.append({
            "name": data.get("name", sid),
            "session_id": sid,
            "session_dir": sdir,
            "rounds": rounds,
            "folder_id": data.get("folder_id", ""),
            "created_at": data.get("created_at", ""),
            "notes_path": data.get("notes_path", ""),
            "project_path": data.get("project_path", ""),
            "hidden": hidden,
            "order": data.get("order", 0),
        })

    # 按 folder_id 分组，组内按 order 排，无 order 的按时间倒序
    grouped = {}
    for s in results:
        grouped.setdefault(s["folder_id"], []).append(s)
    ordered = []
    for fid, items in grouped.items():
        has_custom_order = any(s["order"] != 0 for s in items)
        if has_custom_order:
            items.sort(key=lambda s: s["order"])
        else:
            items.sort(key=lambda s: s["session_id"], reverse=True)
        ordered.extend(items)
    return ordered


def rename_session(session_id: str, new_name: str):
    hfile = _SESSIONS_DIR / session_id / "chat_history.json"
    if not hfile.is_file():
        return
    try:
        data = json.loads(hfile.read_text(encoding="utf-8"))
        data["name"] = new_name
        hfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def toggle_session_hidden(session_ids: list[str]):
    """批量切换 session 的隐藏状态"""
    for sid in session_ids:
        hfile = _SESSIONS_DIR / sid / "chat_history.json"
        if not hfile.is_file():
            continue
        try:
            data = json.loads(hfile.read_text(encoding="utf-8"))
            data["hidden"] = not data.get("hidden", False)
            hfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            continue


def delete_sessions(session_ids: list[str]):
    import shutil
    for sid in session_ids:
        sdir = _SESSIONS_DIR / sid
        if sdir.is_dir():
            shutil.rmtree(sdir, ignore_errors=True)
