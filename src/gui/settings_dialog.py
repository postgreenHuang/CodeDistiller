"""
Code-Distiller 设置对话框
- 基础设置: 主题、AI Provider
- 高级设置: 文件大小限制、分析参数
- 快捷提问管理
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QGroupBox,
    QTextEdit, QSpinBox, QScrollArea, QDialogButtonBox, QWidget,
)

from ..config import load_settings, save_settings


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumSize(560, 480)
        self.settings = settings
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_basic_tab(), "基础")
        tabs.addTab(self._build_advanced_tab(), "高级")
        tabs.addTab(self._build_providers_tab(), "AI 模型")
        tabs.addTab(self._build_quick_questions_tab(), "快捷提问")
        layout.addWidget(tabs)

        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bbox.accepted.connect(self._save_and_accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)

    # ─── 基础 Tab ───

    def _build_basic_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        # 主题
        theme_group = QGroupBox("外观")
        theme_layout = QHBoxLayout(theme_group)
        theme_layout.addWidget(QLabel("主题:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        theme_layout.addWidget(self.theme_combo)
        layout.addWidget(theme_group)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ─── 高级 Tab ───

    def _build_advanced_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        # 分析参数
        params_group = QGroupBox("分析参数")
        params_layout = QVBoxLayout(params_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("文件大小上限 (KB):"))
        self.max_file_size_spin = QSpinBox()
        self.max_file_size_spin.setRange(64, 4096)
        self.max_file_size_spin.setSingleStep(64)
        row1.addWidget(self.max_file_size_spin)
        params_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("每阶段最多文件数:"))
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(5, 100)
        self.max_files_spin.setSingleStep(5)
        row2.addWidget(self.max_files_spin)
        params_layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("默认蒸馏模式:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Normal — 标准分析", "normal")
        self.mode_combo.addItem("High — 深入分析", "high")
        self.mode_combo.addItem("Ultra — 极致分析", "ultra")
        row3.addWidget(self.mode_combo)
        params_layout.addLayout(row3)

        layout.addWidget(params_group)

        # 分析 Prompt
        prompt_group = QGroupBox("蒸馏 Prompt")
        prompt_layout = QVBoxLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setMaximumHeight(200)
        prompt_layout.addWidget(self.prompt_edit)
        layout.addWidget(prompt_group)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    # ─── AI 模型 Tab ───

    def _build_providers_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        hint = QLabel("配置 AI Provider，用于代码分析和对话")
        hint.setProperty("class", "hint")
        layout.addWidget(hint)

        self._providers_container = QWidget()
        self._providers_container.setStyleSheet("background: transparent;")
        self._providers_layout = QVBoxLayout(self._providers_container)
        self._providers_layout.setSpacing(8)
        self._providers_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._providers_container)

        add_btn = QPushButton("+ 新增 Provider")
        add_btn.setProperty("class", "secondary")
        add_btn.clicked.connect(self._add_provider_card)
        layout.addWidget(add_btn)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_provider_card(self, data: dict) -> QGroupBox:
        card = QGroupBox()
        card.setStyleSheet("QGroupBox { margin-top: 10px; }")
        lo = QVBoxLayout(card)
        lo.setSpacing(4)
        lo.setContentsMargins(12, 14, 12, 8)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("名称:"))
        name_edit = QLineEdit(data.get("name", ""))
        name_edit.setPlaceholderText("如: Gemini")
        row1.addWidget(name_edit, stretch=1)
        btn_del = QPushButton("删除")
        btn_del.setFixedWidth(56)
        btn_del.setProperty("class", "secondary")
        row1.addWidget(btn_del)
        lo.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Base URL:"))
        url_edit = QLineEdit(data.get("base_url", ""))
        url_edit.setPlaceholderText("https://api.openai.com/v1")
        row2.addWidget(url_edit, stretch=1)
        lo.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("API Key:"))
        key_edit = QLineEdit(data.get("api_key", ""))
        key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_edit.setPlaceholderText("sk-...")
        row3.addWidget(key_edit, stretch=1)
        lo.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("模型:"))
        model_edit = QLineEdit(data.get("model", ""))
        model_edit.setPlaceholderText("gpt-4o")
        row4.addWidget(model_edit, stretch=1)
        lo.addLayout(row4)

        data["_widgets"] = {"name": name_edit, "url": url_edit, "key": key_edit, "model": model_edit, "card": card}
        btn_del.clicked.connect(lambda checked, d=data: self._del_provider_card(d))
        return card

    def _add_provider_card(self):
        new_data = {"name": "", "base_url": "", "api_key": "", "model": ""}
        self._providers_data.append(new_data)
        card = self._build_provider_card(new_data)
        self._providers_layout.addWidget(card)

    def _del_provider_card(self, data: dict):
        w = data.get("_widgets")
        if w and w.get("card"):
            w["card"].setParent(None)
            w["card"].deleteLater()
        if data in self._providers_data:
            self._providers_data.remove(data)

    def _rebuild_provider_cards(self):
        while self._providers_layout.count():
            item = self._providers_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for data in self._providers_data:
            card = self._build_provider_card(data)
            self._providers_layout.addWidget(card)

    def _collect_provider_data(self):
        for data in self._providers_data:
            w = data.get("_widgets")
            if w:
                data["name"] = w["name"].text()
                data["base_url"] = w["url"].text()
                data["api_key"] = w["key"].text()
                data["model"] = w["model"].text()

    # ─── 快捷提问 Tab ───

    def _build_quick_questions_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setSpacing(8)

        hint = QLabel("添加常用的提问模板，对话界面可一键选用")
        hint.setProperty("class", "hint")
        layout.addWidget(hint)

        self._qq_container = QWidget()
        self._qq_container.setStyleSheet("background: transparent;")
        self._qq_cards_layout = QVBoxLayout(self._qq_container)
        self._qq_cards_layout.setSpacing(8)
        self._qq_cards_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._qq_container)

        btn_add = QPushButton("+ 新增提问")
        btn_add.clicked.connect(self._add_qq_card)
        layout.addWidget(btn_add)

        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_qq_card(self, data: dict) -> QGroupBox:
        card = QGroupBox()
        card.setStyleSheet("QGroupBox { margin-top: 10px; }")
        layout = QVBoxLayout(card)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 14, 12, 8)

        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(QLabel("名称:"))
        name_edit = QLineEdit(data.get("name", ""))
        name_edit.setPlaceholderText("提问名称")
        top.addWidget(name_edit, stretch=1)
        btn_del = QPushButton("删除")
        btn_del.setFixedWidth(56)
        btn_del.setProperty("class", "secondary")
        top.addWidget(btn_del)
        layout.addLayout(top)

        text_edit = QTextEdit()
        text_edit.setPlainText(data.get("text", ""))
        text_edit.setPlaceholderText("输入完整问句")
        text_edit.setMaximumHeight(70)
        layout.addWidget(text_edit)

        data["_widgets"] = {"name": name_edit, "text": text_edit, "card": card}
        btn_del.clicked.connect(lambda checked, d=data: self._del_qq_card(d))
        return card

    def _add_qq_card(self):
        new_data = {"name": "", "text": ""}
        self._qq_data.append(new_data)
        card = self._build_qq_card(new_data)
        self._qq_cards_layout.addWidget(card)

    def _del_qq_card(self, data: dict):
        w = data.get("_widgets")
        if w and w.get("card"):
            w["card"].setParent(None)
            w["card"].deleteLater()
        if data in self._qq_data:
            self._qq_data.remove(data)

    def _rebuild_qq_cards(self):
        while self._qq_cards_layout.count():
            item = self._qq_cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for data in self._qq_data:
            card = self._build_qq_card(data)
            self._qq_cards_layout.addWidget(card)

    def _collect_qq_data(self):
        for data in self._qq_data:
            w = data.get("_widgets")
            if w:
                data["name"] = w["name"].text()
                data["text"] = w["text"].toPlainText()

    # ─── 加载/保存 ───

    def _load_values(self):
        s = self.settings

        self.theme_combo.setCurrentText(s.theme)
        self.max_file_size_spin.setValue(s.max_file_size_kb)
        self.max_files_spin.setValue(s.max_files_per_phase)
        self.prompt_edit.setPlainText(s.default_analysis_prompt)

        idx = self.mode_combo.findData(s.analysis_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        # Providers
        self._providers_data = [dict(p) for p in s.providers]
        self._rebuild_provider_cards()

        # 快捷提问
        self._qq_data = [dict(q) for q in s.quick_questions]
        self._rebuild_qq_cards()

    def _save_and_accept(self):
        self._collect_provider_data()
        self._collect_qq_data()

        s = self.settings
        s.theme = self.theme_combo.currentText()
        s.max_file_size_kb = self.max_file_size_spin.value()
        s.max_files_per_phase = self.max_files_spin.value()
        s.default_analysis_prompt = self.prompt_edit.toPlainText()
        s.analysis_mode = self.mode_combo.currentData() or "normal"

        s.providers = [{k: v for k, v in d.items() if k != "_widgets"} for d in self._providers_data]
        s.quick_questions = [{k: v for k, v in d.items() if k != "_widgets"} for d in self._qq_data]

        save_settings(s)
        self.accept()
