"""
Code-Distiller AI 对话界面
基于 Video-Distiller 对话组件适配，去掉图片相关功能
- 左侧：session 列表（文件夹分组、拖拽排序、搜索）
- 右侧：消息气泡 + 模型切换 + 齿轮配置 + 新建对话
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QTextDocument
from PySide6.QtWidgets import (
    QTreeWidgetItemIterator,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QTextBrowser, QScrollArea, QSizePolicy,
    QTreeWidget, QTreeWidgetItem, QFrame, QComboBox, QFileDialog,
    QMenu, QDialog, QGridLayout, QLineEdit, QDialogButtonBox,
    QInputDialog, QSplitter,
)

from ..chat import (ChatSession, create_session, list_sessions, rename_session,
                    delete_sessions, toggle_session_hidden,
                    load_folders, save_folders, _SESSIONS_DIR)
from ..config import load_settings, save_settings


_THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


# ─── 消息气泡 ───

class MessageBubble(QTextBrowser):
    _font_family = ""
    _font_scale = 100

    def __init__(self, role: str, text: str):
        super().__init__()
        self.setProperty("class", f"msg-{role}")
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self._raw_text = text

        html = self._render_md(text, self._font_family, self._font_scale)
        self.setHtml(html)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._sync_widget_font()
        self.document().documentLayout().documentSizeChanged.connect(self._adjust_size)

    def _adjust_size(self):
        doc_h = int(self.document().documentLayout().documentSize().height())
        target = doc_h + 26
        if abs(self.height() - target) > 2:
            self.setFixedHeight(target)
            self.updateGeometry()

    @staticmethod
    def _render_md(text: str, font_family: str, font_scale: int) -> str:
        import re

        base_px = 14.0 * font_scale / 100.0
        family = font_family if font_family else (
            "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        )
        font = QFont(family)
        font.setPixelSize(int(base_px))

        doc = QTextDocument()
        doc.setDefaultFont(font)
        doc.setMarkdown(text)
        html = doc.toHtml()

        # 调整标题和段落间距
        def _patch(tag, top, bottom):
            nonlocal html
            html = re.sub(
                rf'(<{tag}\s[^>]*?)margin-top:\s*\d+px;(\s*)margin-bottom:\s*\d+px',
                rf'\g<1>margin-top:{top}px;\2margin-bottom:{bottom}px',
                html,
            )

        _patch('h1', 20, 8)
        _patch('h2', 18, 6)
        _patch('h3', 14, 4)
        _patch('p', 4, 4)
        _patch('li', 2, 2)

        # 压缩空段落
        html = re.sub(r'<p\s[^>]*>\s*</p>', '', html)

        return html

    def _apply_font(self):
        html = self._render_md(self._raw_text, self._font_family, self._font_scale)
        self.setHtml(html)
        self._sync_widget_font()

    def _sync_widget_font(self):
        base_px = 14.0 * self._font_scale / 100.0
        family = self._font_family if self._font_family else (
            "PingFang SC" if sys.platform == "darwin" else "Microsoft YaHei UI"
        )
        font = QFont(family)
        font.setPixelSize(int(base_px))
        self.document().setDefaultFont(font)

    @classmethod
    def set_chat_font(cls, family: str, scale: int):
        cls._font_family = family
        cls._font_scale = scale


# ─── 可拖拽排序的 Session 树 ───

class _DraggableTreeWidget(QTreeWidget):
    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        self._drag_item = None

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "session":
            return
        self._drag_item = item
        super().startDrag(supportedActions)

    def dragEnterEvent(self, event):
        if self._drag_item:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._drag_item:
            target = self.itemAt(event.position().toPoint())
            if target:
                target_data = target.data(0, Qt.ItemDataRole.UserRole)
                if target_data and target_data.get("type") == "session":
                    if self._drag_item.parent() is target.parent():
                        event.acceptProposedAction()
                        return
            event.ignore()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not self._drag_item:
            event.ignore()
            return

        target = self.itemAt(event.position().toPoint())
        if not target:
            event.ignore()
            self._drag_item = None
            return

        target_data = target.data(0, Qt.ItemDataRole.UserRole)
        if not target_data or target_data.get("type") != "session":
            event.ignore()
            self._drag_item = None
            return

        if self._drag_item.parent() is not target.parent():
            event.ignore()
            self._drag_item = None
            return

        event.acceptProposedAction()

        parent = self._drag_item.parent()
        children = [parent.child(i) for i in range(parent.childCount())]

        drag_idx = children.index(self._drag_item) if self._drag_item in children else -1
        target_idx = children.index(target) if target in children else -1
        if drag_idx < 0 or target_idx < 0 or drag_idx == target_idx:
            self._drag_item = None
            return

        rect = self.visualItemRect(target)
        drop_pos = "above" if event.position().toPoint().y() < rect.center().y() else "below"

        item = children.pop(drag_idx)
        new_target_idx = children.index(target) if target in children else 0
        insert_idx = new_target_idx if drop_pos == "above" else new_target_idx + 1
        children.insert(insert_idx, item)

        for i in range(parent.childCount()):
            parent.takeChild(0)
        for child in children:
            parent.addChild(child)

        self._persist_order()
        self._drag_item = None
        self.orderChanged.emit()

    def _persist_order(self):
        from ..chat import _SESSIONS_DIR

        order_map = {}
        idx = 0
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "session":
                order_map[data["session_id"]] = idx
                idx += 1
            it.__next__()

        for sid, order in order_map.items():
            hfile = _SESSIONS_DIR / sid / "chat_history.json"
            if not hfile.is_file():
                continue
            try:
                d = json.loads(hfile.read_text(encoding="utf-8"))
                d["order"] = order
                hfile.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass


# ─── 后台对话线程 ───

class _ChatWorker(QThread):
    finished = Signal(str, int)
    error = Signal(str)
    reading_files = Signal(list)  # AI 正在读取的文件路径列表
    status_update = Signal(str)   # agent loop 状态: "analyzing", "fallback"

    def __init__(self, session: ChatSession, message: str):
        super().__init__()
        self.session = session
        self.message = message
        self._cancel = False

    def run(self):
        try:
            reply = self.session.chat(
                self.message,
                on_read_files=lambda paths: self.reading_files.emit(paths),
                on_status=lambda s: self.status_update.emit(s),
            )
            if self._cancel:
                return
            total = sum(len(m["content"]) for m in self.session.messages)
            self.finished.emit(reply, total)
        except Exception as e:
            if not self._cancel:
                self.error.emit(str(e))


# ─── 对话配置对话框 ───

class _SessionConfigDialog(QDialog):
    def __init__(self, session: ChatSession, parent=None):
        super().__init__(parent)
        self.setWindowTitle("对话配置")
        self.setMinimumWidth(480)
        self.session = session

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        grid.addWidget(QLabel("蒸馏笔记 (notes.md):"), 0, 0)
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("选择笔记文件...")
        self.notes_edit.setText(session.notes_path)
        grid.addWidget(self.notes_edit, 0, 1)
        btn_notes = QPushButton("浏览")
        btn_notes.setProperty("class", "secondary")
        btn_notes.setFixedWidth(56)
        btn_notes.clicked.connect(lambda: self._browse(self.notes_edit, "笔记文件", "Markdown (*.md);;所有文件 (*)"))
        grid.addWidget(btn_notes, 0, 2)

        grid.addWidget(QLabel("项目文件夹:"), 1, 0)
        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("选择项目文件夹...")
        self.project_edit.setText(session.project_path)
        grid.addWidget(self.project_edit, 1, 1)
        btn_proj = QPushButton("浏览")
        btn_proj.setProperty("class", "secondary")
        btn_proj.setFixedWidth(56)
        btn_proj.clicked.connect(lambda: self._browse_dir(self.project_edit))
        grid.addWidget(btn_proj, 1, 2)

        layout.addLayout(grid)

        hint = QLabel("项目文件夹用于提供关键源码作为对话上下文。笔记将作为对话首条消息显示。")
        hint.setProperty("class", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        bbox = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _browse(self, edit: QLineEdit, title: str, filter: str):
        path, _ = QFileDialog.getOpenFileName(self, title, "", filter)
        if path:
            edit.setText(path)

    def _browse_dir(self, edit: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if path:
            edit.setText(path)

    def get_paths(self) -> tuple:
        return self.notes_edit.text().strip(), self.project_edit.text().strip()


# ─── 快捷提问编辑器 ───

class _QuickQuestionsDialog(QDialog):
    def __init__(self, questions: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑快捷提问")
        self.setMinimumWidth(420)
        self.setMinimumHeight(200)
        layout = QVBoxLayout(self)

        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(6)
        self._rows = []
        for q in questions:
            self._create_row(q.get("name", ""), q.get("text", ""))

        layout.addLayout(self._rows_layout)

        add_btn = QPushButton("+ 添加快捷提问")
        add_btn.setProperty("class", "secondary")
        add_btn.clicked.connect(self._add_row)
        layout.addWidget(add_btn)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    def _create_row(self, name: str, text: str):
        row_layout = QHBoxLayout()
        row_layout.setSpacing(6)
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText("名称")
        name_edit.setFixedWidth(200)
        text_edit = QLineEdit(text)
        text_edit.setPlaceholderText("提问内容")
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setProperty("class", "secondary")
        row_layout.addWidget(name_edit)
        row_layout.addWidget(text_edit)
        row_layout.addWidget(del_btn)
        self._rows_layout.addLayout(row_layout)
        row = (name_edit, text_edit, row_layout)
        self._rows.append(row)
        del_btn.clicked.connect(lambda checked=False, r=row: self._remove_row(r))

    def _add_row(self):
        self._create_row("", "")
        self.adjustSize()

    def _remove_row(self, row):
        name_edit, text_edit, row_layout = row
        while row_layout.count():
            item = row_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._rows_layout.removeItem(row_layout)
        if row in self._rows:
            self._rows.remove(row)
        self.adjustSize()

    def get_questions(self) -> list[dict]:
        result = []
        for name_edit, text_edit, _ in self._rows:
            name = name_edit.text().strip()
            text = text_edit.text().strip()
            if name and text:
                result.append({"name": name, "text": text})
        return result


# ─── 对话主组件 ───

class ChatWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.session: Optional[ChatSession] = None
        self._worker: Optional[_ChatWorker] = None
        self._provider_config: dict = {}
        self._all_providers: list = []
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(150)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._thinking_frame = 0
        self._thinking_start = 0.0
        self._thinking_bubble: Optional[MessageBubble] = None
        self._show_hidden = False
        self._build_ui()

    def _build_ui(self):
        # ─── 左侧：session 列表 ───
        left_panel = QWidget()
        left_panel.setProperty("class", "chat-sidebar")
        left_panel.setMinimumWidth(140)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        # 顶部按钮行
        top_bar = QWidget()
        top_bar.setProperty("class", "chat-sidebar-top")
        top_bar.setFixedHeight(36)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("对话历史")
        title.setProperty("class", "sidebar-title")
        top_layout.addWidget(title)
        top_layout.addStretch()

        self.btn_new_folder = QPushButton("📁")
        self.btn_new_folder.setFixedSize(28, 28)
        self.btn_new_folder.setProperty("class", "secondary")
        self.btn_new_folder.setToolTip("新建文件夹")
        self.btn_new_folder.clicked.connect(self._on_new_folder)
        top_layout.addWidget(self.btn_new_folder)

        self.btn_new_chat = QPushButton("＋")
        self.btn_new_chat.setFixedSize(28, 28)
        self.btn_new_chat.setProperty("class", "secondary")
        self.btn_new_chat.setToolTip("新建对话")
        self.btn_new_chat.clicked.connect(self._on_new_chat)
        top_layout.addWidget(self.btn_new_chat)

        self.btn_show_hidden = QPushButton("👁")
        self.btn_show_hidden.setFixedSize(28, 28)
        self.btn_show_hidden.setProperty("class", "secondary")
        self.btn_show_hidden.setToolTip("显示隐藏的对话")
        self.btn_show_hidden.clicked.connect(self._toggle_show_hidden)
        top_layout.addWidget(self.btn_show_hidden)

        left_layout.addWidget(top_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("class", "chat-sep")
        sep.setFixedHeight(1)
        left_layout.addWidget(sep)

        # 搜索框
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索对话...")
        self._search_edit.setProperty("class", "chat-search")
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_changed)
        left_layout.addWidget(self._search_edit)

        # Session 树
        self.session_tree = _DraggableTreeWidget()
        self.session_tree.setProperty("class", "session-tree")
        self.session_tree.setHeaderHidden(True)
        self.session_tree.setIndentation(16)
        self.session_tree.setAnimated(True)
        self.session_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.session_tree.currentItemChanged.connect(self._on_tree_item_changed)
        self.session_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.session_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.session_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        left_layout.addWidget(self.session_tree, 1)

        # ─── 右侧：聊天区 ───
        right_panel = QWidget()
        right_panel.setProperty("class", "chat-right")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 状态栏
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("选择或新建一个对话")
        self.status_label.setProperty("class", "chat-status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFixedHeight(32)
        status_row.addWidget(self.status_label, 1)

        self.btn_config = QPushButton("⚙")
        self.btn_config.setFixedSize(28, 28)
        self.btn_config.setProperty("class", "secondary")
        self.btn_config.setToolTip("配置关联文件")
        self.btn_config.clicked.connect(self._on_config)
        status_row.addWidget(self.btn_config)

        right_layout.addLayout(status_row)

        # 关联文件指示
        self.files_label = QLabel("")
        self.files_label.setProperty("class", "hint")
        self.files_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.files_label.setFixedHeight(22)
        self.files_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.files_label.mousePressEvent = self._on_files_label_click
        right_layout.addWidget(self.files_label)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setProperty("class", "chat-sep")
        sep2.setFixedHeight(1)
        right_layout.addWidget(sep2)

        # 消息列表
        self.scroll = QScrollArea()
        self.scroll.setProperty("class", "chat-scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.messages_widget = QWidget()
        self.messages_widget.setProperty("class", "chat-messages")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.messages_layout.setSpacing(16)
        self.messages_layout.setContentsMargins(20, 16, 20, 16)
        self.messages_layout.addStretch()

        self.scroll.setWidget(self.messages_widget)
        right_layout.addWidget(self.scroll, 1)

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setProperty("class", "chat-sep")
        sep3.setFixedHeight(1)
        right_layout.addWidget(sep3)

        # 输入区域
        input_bar = QWidget()
        input_bar.setProperty("class", "chat-input-bar")
        input_layout = QVBoxLayout(input_bar)
        input_layout.setContentsMargins(16, 10, 16, 10)
        input_layout.setSpacing(8)

        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("输入你的问题...")
        self.input_edit.setFixedHeight(72)
        self.input_edit.setMaximumHeight(100)
        self.input_edit.installEventFilter(self)
        input_layout.addWidget(self.input_edit)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.token_label = QLabel("")
        self.token_label.setProperty("class", "hint")
        bottom_row.addWidget(self.token_label)
        bottom_row.addStretch()

        self.quick_btn = QPushButton("快捷提问")
        self.quick_btn.setProperty("class", "chat-quick-btn")
        self.quick_btn.setFixedWidth(80)
        self.quick_btn.clicked.connect(self._show_quick_menu)
        self.quick_btn.setStyleSheet("padding: 3px 6px;")
        bottom_row.addWidget(self.quick_btn)

        self.quick_edit_btn = QPushButton("✏")
        self.quick_edit_btn.setFixedSize(26, 26)
        self.quick_edit_btn.setProperty("class", "secondary")
        self.quick_edit_btn.setToolTip("编辑快捷提问")
        self.quick_edit_btn.clicked.connect(self._edit_quick_questions)
        bottom_row.addWidget(self.quick_edit_btn)

        self.model_combo = QComboBox()
        self.model_combo.setProperty("class", "chat-model-combo")
        self.model_combo.setFixedWidth(160)
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        bottom_row.addWidget(self.model_combo)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(80)
        self.send_btn.clicked.connect(self._on_send)
        bottom_row.addWidget(self.send_btn)

        input_layout.addLayout(bottom_row)
        right_layout.addWidget(input_bar)

        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(3)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([220, 600])
        splitter.setStretchFactor(1, 1)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(splitter)

        # 启动时加载已有对话
        self._build_session_tree()

    # ─── Provider ───

    def set_providers(self, providers: list):
        self._all_providers = [dict(p) for p in providers if p.get("api_key")]
        self._refresh_model_combo()

    def apply_font_settings(self, family: str, scale: int):
        MessageBubble.set_chat_font(family, scale)
        for i in range(self.messages_layout.count()):
            item = self.messages_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageBubble):
                item.widget()._apply_font()

    def _refresh_model_combo(self):
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        providers = self._all_providers
        if not providers:
            providers = [dict(p) for p in load_settings().providers if p.get("api_key")]
        for p in providers:
            self.model_combo.addItem(f"{p.get('name', '')}: {p.get('model', '')}", p)
        if self._provider_config:
            for i in range(self.model_combo.count()):
                if (self.model_combo.itemData(i).get("base_url") == self._provider_config.get("base_url")
                        and self.model_combo.itemData(i).get("model") == self._provider_config.get("model")):
                    self.model_combo.setCurrentIndex(i)
                    break
        self.model_combo.blockSignals(False)

    def _on_model_changed(self, index: int):
        if index < 0:
            return
        config = self.model_combo.itemData(index)
        if config:
            self._provider_config = config
            if self.session:
                self.session.provider = config
                self.session.base_url = config.get("base_url", "").rstrip("/")
                self.session.api_key = config.get("api_key", "")
                self.session.model = config.get("model", "")

    # ─── Session 列表 ───

    def refresh_session_list(self, provider_config: dict):
        self._provider_config = provider_config
        self._build_session_tree()

    def _build_session_tree(self):
        self.session_tree.clear()
        sessions = list_sessions(show_hidden=self._show_hidden)
        search_text = self._search_edit.text().strip().lower()

        if search_text:
            sessions = [s for s in sessions if search_text in s.get("name", "").lower()]

        folders = load_folders()

        # 构建用户文件夹节点
        folder_map = {}
        for f in folders:
            item = QTreeWidgetItem(self.session_tree, [f["name"]])
            item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": f["id"], "name": f["name"]})
            item.setExpanded(True)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            folder_map[f["id"]] = item

        # 分配 session 到文件夹或根级
        for s in sessions:
            fid = s.get("folder_id", "")
            if fid and fid in folder_map:
                self._add_session_item(folder_map[fid], s)
            else:
                self._add_session_item(self.session_tree.invisibleRootItem(), s)

    def _on_search_changed(self, text: str):
        self._build_session_tree()

    def _add_session_item(self, parent, s: dict):
        rounds_str = f" ({s['rounds']}轮)" if s["rounds"] > 0 else ""
        label = f"{s['name']}{rounds_str}"
        item = QTreeWidgetItem(parent, [label])
        item.setData(0, Qt.ItemDataRole.UserRole, {"type": "session", **s})

    def _toggle_show_hidden(self):
        self._show_hidden = not self._show_hidden
        self.btn_show_hidden.setText("👁‍🗨" if self._show_hidden else "👁")
        self._build_session_tree()

    def _on_tree_item_changed(self, current: QTreeWidgetItem, _prev):
        if not current:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "session":
            return

        info = data
        session_dir = info["session_dir"]
        self.session = ChatSession(session_dir, self._provider_config)
        self.session._load_history()

        n_msgs = sum(1 for m in self.session.messages if m.get("role") == "user")
        self.status_label.setText(f"{self.session.name} | {self.session.model} | {n_msgs} 轮")
        self._update_files_label()
        self._restore_history()

    def _update_files_label(self):
        parts = []
        if self.session:
            if self.session.notes_path and os.path.exists(self.session.notes_path):
                parts.append("notes ✓")
            else:
                parts.append("notes ✗")
            if self.session.project_path and os.path.isdir(self.session.project_path):
                parts.append("项目 ✓")
            else:
                parts.append("项目 ✗")
        self.files_label.setText("  |  ".join(parts))

    def _on_files_label_click(self, event):
        if not self.session:
            return
        if self.session.notes_path and os.path.exists(self.session.notes_path):
            os.startfile(self.session.notes_path)

    def _on_tree_context_menu(self, pos):
        item = self.session_tree.itemAt(pos)
        menu = QMenu(self)

        if not item:
            menu.addAction("新建文件夹", self._on_new_folder)
            menu.addSeparator()
            menu.addAction("导入对话...", self._on_import_sessions)
            menu.exec(self.session_tree.mapToGlobal(pos))
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)

        if data.get("type") == "folder":
            menu.addAction("重命名", lambda: self._rename_folder(data["id"], item))
            menu.addAction("删除文件夹", lambda: self._delete_folder(data["id"]))
            menu.exec(self.session_tree.mapToGlobal(pos))
            return

        # Session 项
        selected = self.session_tree.selectedItems()
        session_items = [si for si in selected
                         if si.data(0, Qt.ItemDataRole.UserRole).get("type") == "session"]
        if not session_items:
            return

        n = len(session_items)

        # 隐藏/取消隐藏
        if n == 1:
            is_hidden = session_items[0].data(0, Qt.ItemDataRole.UserRole).get("hidden", False)
            hide_label = "取消隐藏" if is_hidden else "隐藏"
            menu.addAction(hide_label, lambda: self._toggle_hidden(session_items))
        else:
            menu.addAction("隐藏选中的对话", lambda: self._toggle_hidden(session_items))

        # 删除
        label = f"删除选中的 {n} 个对话" if n > 1 else "删除此对话"
        menu.addAction(label, lambda: self._delete_sessions(session_items))

        # 导出
        if n == 1:
            menu.addAction("导出对话...", lambda: self._on_export_sessions(session_items))

        # 移动到文件夹
        folders = load_folders()
        if folders:
            move_menu = menu.addMenu("移动到")
            for f in folders:
                move_menu.addAction(f["name"],
                    lambda checked=False, fid=f["id"]: self._move_sessions(session_items, fid))
            move_menu.addSeparator()
            move_menu.addAction("移出文件夹",
                lambda: self._move_sessions(session_items, ""))

        menu.exec(self.session_tree.mapToGlobal(pos))

    def _on_new_folder(self):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称：")
        if not ok or not name.strip():
            return
        folders = load_folders()
        folder_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        folders.append({"id": folder_id, "name": name.strip()})
        save_folders(folders)
        self._build_session_tree()

    def _rename_folder(self, folder_id: str, item: QTreeWidgetItem):
        old_name = item.text(0)
        name, ok = QInputDialog.getText(self, "重命名文件夹", "新名称：", text=old_name)
        if not ok or not name.strip():
            return
        folders = load_folders()
        for f in folders:
            if f["id"] == folder_id:
                f["name"] = name.strip()
                break
        save_folders(folders)
        self._build_session_tree()

    def _delete_folder(self, folder_id: str):
        folders = load_folders()
        folders = [f for f in folders if f["id"] != folder_id]
        save_folders(folders)
        # 将该文件夹下的 session 移回根级
        if _SESSIONS_DIR.is_dir():
            for sid in os.listdir(str(_SESSIONS_DIR)):
                hfile = _SESSIONS_DIR / sid / "chat_history.json"
                if hfile.is_file():
                    try:
                        d = json.loads(hfile.read_text(encoding="utf-8"))
                        if d.get("folder_id") == folder_id:
                            d["folder_id"] = ""
                            hfile.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass
        self._build_session_tree()

    def _move_sessions(self, items: list, folder_id: str):
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data.get("type") != "session":
                continue
            hfile = _SESSIONS_DIR / data["session_id"] / "chat_history.json"
            if hfile.is_file():
                try:
                    d = json.loads(hfile.read_text(encoding="utf-8"))
                    d["folder_id"] = folder_id
                    hfile.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        self._build_session_tree()

    def _toggle_hidden(self, items: list):
        session_ids = []
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data.get("type") == "session":
                session_ids.append(data["session_id"])
        if session_ids:
            toggle_session_hidden(session_ids)
            self._build_session_tree()

    def _on_export_sessions(self, items: list):
        from ..session_io import export_sessions
        session_ids = []
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data.get("type") == "session":
                session_ids.append(data["session_id"])
        if not session_ids:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "导出对话", "", "Code-Distiller 对话包 (*.cdc)"
        )
        if not dest:
            return
        if not dest.endswith(".cdc"):
            dest += ".cdc"
        try:
            ok = export_sessions(session_ids, dest)
            if ok:
                self.status_label.setText(f"已导出 {len(session_ids)} 个对话")
            else:
                self.status_label.setText("导出失败：没有可导出的对话")
        except Exception as e:
            self.status_label.setText(f"导出失败：{e}")

    def _on_import_sessions(self):
        from ..session_io import import_sessions
        path, _ = QFileDialog.getOpenFileName(
            self, "导入对话", "", "Code-Distiller 对话包 (*.cdc)"
        )
        if not path:
            return
        try:
            new_ids = import_sessions(path)
            if new_ids:
                self._build_session_tree()
                self.status_label.setText(f"已导入 {len(new_ids)} 个对话")
            else:
                self.status_label.setText("导入失败：文件中没有可导入的对话")
        except Exception as e:
            self.status_label.setText(f"导入失败：{e}")

    def _delete_sessions(self, items: list):
        import shutil
        for item in items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data.get("type") != "session":
                continue
            session_dir = data["session_dir"]
            if self.session and self.session.session_dir == session_dir:
                self.session = None
                self._clear_messages()
                self.status_label.setText("选择或新建一个对话")
                self.files_label.setText("")
            shutil.rmtree(session_dir, ignore_errors=True)
        self._build_session_tree()

    def _on_tree_double_click(self, item: QTreeWidgetItem, _col: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "session":
            return
        old_name = data.get("name", "")
        name, ok = QInputDialog.getText(self, "重命名对话", "新名称：", text=old_name)
        if not ok or not name.strip() or name.strip() == old_name:
            return
        rename_session(data["session_id"], name.strip())
        data["name"] = name.strip()
        rounds_str = f" ({data.get('rounds', 0)}轮)" if data.get("rounds", 0) > 0 else ""
        item.setText(0, f"{name.strip()}{rounds_str}")
        item.setData(0, Qt.ItemDataRole.UserRole, data)
        if self.session and self.session.session_dir == data.get("session_dir"):
            self.session.name = name.strip()
            n_msgs = sum(1 for m in self.session.messages if m.get("role") == "user")
            self.status_label.setText(f"{self.session.name} | {self.session.model} | {n_msgs} 轮")

    # ─── 新建对话 ───

    def _on_new_chat(self):
        project_path = getattr(self, '_current_project_path', '')
        output_dir = getattr(self, '_current_output_dir', '')

        # 查找蒸馏笔记
        notes_path = ""
        if output_dir and project_path:
            notes_dir = os.path.join(output_dir, Path(project_path).name, "notes")
            if os.path.isdir(notes_dir):
                for f in sorted(os.listdir(notes_dir), reverse=True):
                    if f.endswith(".md"):
                        notes_path = os.path.join(notes_dir, f)
                        break

        session = create_session(
            project_path=project_path,
            notes_path=notes_path,
            provider_config=self._provider_config,
        )
        self.session = session

        self._build_session_tree()
        self._select_session_in_tree(session.session_dir)

        self.status_label.setText(f"{session.name} | 点击 ⚙ 配置文件")
        self._update_files_label()
        self._clear_messages()
        if session.messages:
            self._restore_history()

    def _select_session_in_tree(self, session_dir: str):
        it = QTreeWidgetItemIterator(self.session_tree)
        while it.value():
            item = it.value()
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data.get("type") == "session" and data.get("session_dir") == session_dir:
                self.session_tree.setCurrentItem(item)
                return
            it.__next__()

    # ─── 齿轮配置 ───

    def _on_config(self):
        if not self.session:
            self.status_label.setText("请先选择或新建一个对话")
            return

        dlg = _SessionConfigDialog(self.session, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        notes_path, project_path = dlg.get_paths()
        self.session.update_files(notes_path, project_path)

        self._update_files_label()
        self._restore_history()
        self._refresh_session_name()

        n_msgs = sum(1 for m in self.session.messages if m.get("role") == "user")
        self.status_label.setText(f"{self.session.name} | {self.session.model} | {n_msgs} 轮")

    def _refresh_session_name(self):
        item = self.session_tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "session":
            return
        rounds = sum(1 for m in self.session.messages if m.get("role") == "user") if self.session else 0
        name = self.session.name if self.session else data.get("name", "")
        label = f"{name} ({rounds}轮)" if rounds > 0 else name
        item.setText(0, label)
        data["name"] = name
        if self.session:
            data["notes_path"] = self.session.notes_path
            data["project_path"] = self.session.project_path
        item.setData(0, Qt.ItemDataRole.UserRole, data)

    # ─── 消息 ───

    def _restore_history(self):
        self._clear_messages()
        if not self.session:
            return
        for msg in self.session.messages:
            self._add_bubble(msg["role"], msg["content"])

    def eventFilter(self, obj, event):
        if obj is self.input_edit and event.type() == event.Type.KeyPress:
            key = event.key()
            mod = event.modifiers()
            if key == Qt.Key.Key_Return and not (mod & Qt.KeyboardModifier.ShiftModifier or mod & Qt.KeyboardModifier.ControlModifier):
                self._on_send()
                return True
            if key == Qt.Key.Key_Escape:
                self._on_cancel_send()
                return True
        return super().eventFilter(obj, event)

    def _show_quick_menu(self):
        menu = QMenu(self)
        questions = load_settings().quick_questions
        for q in questions:
            name = q.get("name", "")
            text = q.get("text", "")
            if name and text:
                action = menu.addAction(name)
                action.setData(text)
        if menu.actions():
            menu.triggered.connect(self._on_quick_question)
            menu.exec(self.quick_btn.mapToGlobal(self.quick_btn.rect().bottomLeft()))

    def _on_quick_question(self, action):
        text = action.data()
        if not text:
            return
        current = self.input_edit.toPlainText().strip()
        if current:
            self.input_edit.setPlainText(current + "\n" + text)
        else:
            self.input_edit.setPlainText(text)
        self.input_edit.setFocus()

    def _edit_quick_questions(self):
        settings = load_settings()
        dlg = _QuickQuestionsDialog(settings.quick_questions, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            settings.quick_questions = dlg.get_questions()
            save_settings(settings)

    def _on_send(self):
        if not self.session:
            return
        if self._worker and self._worker.isRunning():
            self._on_cancel_send()
            return
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        self.input_edit.clear()
        self._add_bubble("user", text)

        self.send_btn.setText("取消")
        self.send_btn.clicked.disconnect()
        self.send_btn.clicked.connect(self._on_cancel_send)
        self.input_edit.setEnabled(False)
        self.model_combo.setEnabled(False)
        self.session_tree.setEnabled(False)

        self._thinking_bubble = MessageBubble("assistant", "")
        self._insert_widget(self._thinking_bubble)
        self._thinking_start = time.time()
        self._thinking_frame = 0
        self._thinking_timer.start()

        self._worker = _ChatWorker(self.session, text)
        self._worker.finished.connect(self._on_reply)
        self._worker.error.connect(self._on_error)
        self._worker.reading_files.connect(self._on_reading_files)
        self._worker.status_update.connect(self._on_agent_status)
        self._worker.start()

    def _on_cancel_send(self):
        if not self._worker or not self._worker.isRunning():
            return
        self._worker._cancel = True
        self._stop_thinking()
        self._restore_send_btn()
        self.input_edit.setFocus()
        self.status_label.setText("已取消")

    def _tick_thinking(self):
        if not self._thinking_bubble:
            return
        elapsed = time.time() - self._thinking_start
        s = int(elapsed)
        t = f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"
        frame = _THINKING_FRAMES[self._thinking_frame % len(_THINKING_FRAMES)]
        self._thinking_frame += 1
        self._thinking_bubble.setText(f"{frame} 思考中... {t}")
        self._scroll_to_bottom()

    def _stop_thinking(self):
        self._thinking_timer.stop()
        if self._thinking_bubble:
            idx = self.messages_layout.indexOf(self._thinking_bubble)
            if idx >= 0:
                self.messages_layout.takeAt(idx)
            self._thinking_bubble.setParent(None)
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None

    def _on_reading_files(self, file_paths: list):
        """AI agent loop 请求读文件时更新思考动画"""
        if self._thinking_bubble:
            files_str = ", ".join(Path(p).name for p in file_paths[:5])
            if len(file_paths) > 5:
                files_str += f" ... 等 {len(file_paths)} 个"
            frame = _THINKING_FRAMES[self._thinking_frame % len(_THINKING_FRAMES)]
            self._thinking_bubble.setText(f"{frame} 正在读取: {files_str}")
            self._scroll_to_bottom()

    def _on_agent_status(self, status: str):
        """Agent loop 状态更新"""
        if not self._thinking_bubble:
            return
        elapsed = time.time() - self._thinking_start
        s = int(elapsed)
        t = f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"
        frame = _THINKING_FRAMES[self._thinking_frame % len(_THINKING_FRAMES)]
        if status == "analyzing":
            self._thinking_bubble.setText(f"{frame} 已读取文件，正在分析... {t}")
        elif status == "fallback":
            self._thinking_bubble.setText(f"{frame} 文件未找到，正在基于已有信息回答... {t}")
        self._scroll_to_bottom()

    def _on_reply(self, reply: str, total_chars: int):
        self._stop_thinking()
        self._add_bubble("assistant", reply)
        self._restore_send_btn()
        self.input_edit.setFocus()

        elapsed = time.time() - self._thinking_start
        n_msgs = sum(1 for m in self.session.messages if m.get("role") == "user")
        self.status_label.setText(f"{self.session.name} | {self.session.model} | {n_msgs} 轮")
        self.token_label.setText(f"~{total_chars} chars | {elapsed:.1f}s")
        self._update_current_item_rounds(n_msgs)

    def _on_error(self, err: str):
        self._stop_thinking()
        self._add_bubble("assistant", f"[错误] {err}")
        self._restore_send_btn()
        self.status_label.setText(f"请求失败: {err[:60]}")

    def _restore_send_btn(self):
        self.send_btn.setText("发送")
        try:
            self.send_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self.send_btn.clicked.connect(self._on_send)
        self.send_btn.setEnabled(True)
        self.input_edit.setEnabled(True)
        self.model_combo.setEnabled(True)
        self.session_tree.setEnabled(True)

    def _update_current_item_rounds(self, rounds: int):
        item = self.session_tree.currentItem()
        if not item:
            return
        data = item.getData(0, Qt.ItemDataRole.UserRole) if hasattr(item, 'getData') else item.data(0, Qt.ItemDataRole.UserRole)
        if not data or data.get("type") != "session":
            return
        base = data.get("name", "")
        label = f"{base} ({rounds}轮)" if rounds > 0 else base
        item.setText(0, label)

    # ─── UI 工具 ───

    def _get_bubble_max_width(self) -> int:
        viewport_w = self.scroll.viewport().width()
        return max(viewport_w - 32, 200)

    def _insert_widget(self, widget):
        if isinstance(widget, MessageBubble):
            widget.setMaximumWidth(self._get_bubble_max_width())
        idx = self.messages_layout.count() - 1
        self.messages_layout.insertWidget(idx, widget)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _add_bubble(self, role: str, text: str):
        bubble = MessageBubble(role, text)
        self._insert_widget(bubble)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        max_w = self._get_bubble_max_width()
        for i in range(self.messages_layout.count()):
            item = self.messages_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), MessageBubble):
                item.widget().setMaximumWidth(max_w)

    def _scroll_to_bottom(self):
        sb = self.scroll.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 60
        if at_bottom:
            sb.setValue(sb.maximum())

    def _clear_messages(self):
        while self.messages_layout.count() > 1:
            item = self.messages_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    # ─── 外部接口 ───

    def try_load_project(self, project_path: str, output_dir: str):
        """由主窗口调用，传入当前项目和输出目录"""
        if not project_path or not os.path.isdir(project_path):
            return
        self._current_project_path = project_path
        self._current_output_dir = output_dir

        if self.session:
            notes_path = ""
            project_name = Path(project_path).name
            notes_dir = os.path.join(output_dir, project_name, "notes")
            if os.path.isdir(notes_dir):
                for f in sorted(os.listdir(notes_dir), reverse=True):
                    if f.endswith(".md"):
                        notes_path = os.path.join(notes_dir, f)
                        break
            if notes_path:
                self.session.update_files(notes_path, project_path)
                self.status_label.setText(f"已加载: {self.session.name}")
                self._update_files_label()
        else:
            self.status_label.setText(f"项目: {Path(project_path).name} — 点击 + 新建对话")

    def refresh_providers(self):
        self._refresh_model_combo()
