"""
Code-Distiller 主窗口
布局完全对齐 Video-Distiller 风格:
- 顶部 Toolbar: Settings + Light/Dark 切换
- 路径栏: 项目文件夹 + 输出目录
- 中部左: 项目文件夹列表 (拖拽)
- 中部右: AI Provider 选择 + 开始按钮 + 进度
- 底部: 运行日志
- 顶层两 Tab: 批量蒸馏 / 对话
"""

import os
import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QLineEdit, QPushButton, QTextEdit,
    QProgressBar, QFileDialog, QComboBox, QListWidget,
    QListView, QGridLayout, QToolBar, QToolButton,
)

from ..config import load_settings, save_settings, get_project_output_dir
from ..scanner import scan_project, ScanResult
from ..analyzer import (
    analyze_structure, analyze_algorithms, generate_notes,
    select_files_for_analysis, select_core_files_from_analysis,
    _collect_source_files,
)
from .chat_widget import ChatWidget
from .settings_dialog import SettingsDialog
from .theme import build_stylesheet


# ─── 可拖拽文件夹列表 ───

class _DropFolderList(QListWidget):
    """支持拖拽文件夹的 QListWidget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isdir(path):
                # 去重
                existing = [self.item(i).text() for i in range(self.count())]
                if path not in existing:
                    self.addItem(path)
        event.acceptProposedAction()


# ─── 后台分析线程 ───

class _AnalysisWorker(QThread):
    """批量蒸馏后台线程，逐个项目逐个阶段执行"""
    log = Signal(str)          # 日志消息
    progress = Signal(str)     # 状态消息
    done = Signal()            # 全部完成
    error = Signal(str)        # 错误

    def __init__(self, folders: list[str], output_dir: str, provider: dict,
                  mode: str = "normal"):
        super().__init__()
        self.folders = folders
        self.output_base = output_dir
        self.provider = provider
        self.mode = mode
        self._cancel = False

    def run(self):
        import time
        for folder in self.folders:
            if self._cancel:
                break
            project_name = Path(folder).name
            self.log.emit(f"\n{'='*50}\n开始分析: {project_name}\n{'='*50}")

            output_dir = str(get_project_output_dir(self.output_base, folder))
            phase_results = {}
            scan_result = None

            # Phase 1: 扫描 (本地)
            if self._cancel:
                break
            self.progress.emit(f"[{project_name}] Phase 1/4: 扫描项目...")
            self.log.emit(f"\n--- Phase 1: 项目扫描 ---")
            try:
                result = scan_project(folder, progress_cb=lambda m: self.log.emit(f"  {m}"))
                scan_result = result
                output_path = os.path.join(output_dir, "scan", "scan_result.json")
                result.to_json(output_path)
                summary = result.summary_text(mode=self.mode)
                phase_results["scan"] = summary
                self.log.emit(f"  扫描完成: {result.code_stats.get('total_files', 0)} 文件, "
                              f"{result.code_stats.get('total_lines', 0)} 行代码")
                stats = result.code_stats
                langs = result.languages
                if langs:
                    top_lang = max(langs.items(), key=lambda x: x[1].get("lines", 0))
                    self.log.emit(f"  主要语言: {top_lang[0]} ({top_lang[1].get('lines', 0)} 行)")
            except Exception as e:
                self.log.emit(f"  ✗ 扫描失败: {e}")
                continue

            # Phase 2: 结构分析 (AI)
            if self._cancel:
                break
            self.progress.emit(f"[{project_name}] Phase 2/4: 结构分析...")
            self.log.emit(f"\n--- Phase 2: 结构分析 ---")
            try:
                settings = load_settings()
                entry_files = select_files_for_analysis(folder, scan_result, phase=2, mode=self.mode)
                entry_contents = _collect_source_files(
                    folder, entry_files,
                    max_files=settings.max_files_per_phase,
                    max_size_kb=settings.max_file_size_kb,
                )
                result_text, tokens = analyze_structure(
                    phase_results["scan"], entry_contents,
                    self.provider, progress_cb=lambda m: self.log.emit(f"  {m}"),
                    mode=self.mode,
                )
                phase_results["structure"] = result_text
                Path(os.path.join(output_dir, "analysis", "structure.md")).write_text(result_text, encoding="utf-8")
                self.log.emit(f"  ✓ 完成 (tokens: {tokens.get('input_tokens', 0)}+{tokens.get('output_tokens', 0)})")
            except Exception as e:
                self.log.emit(f"  ✗ 失败: {e}")
                continue

            # Phase 3: 算法深挖 (AI)
            if self._cancel:
                break
            self.progress.emit(f"[{project_name}] Phase 3/4: 算法深挖...")
            self.log.emit(f"\n--- Phase 3: 算法深挖 ---")
            try:
                settings = load_settings()
                core_files = select_core_files_from_analysis(phase_results["structure"], folder)
                # high/ultra 模式：补充 hub 文件和角色关键文件
                if self.mode in ("high", "ultra"):
                    hub_paths = [h["path"] for h in (scan_result.hub_files or [])]
                    core_files.extend(h for h in hub_paths[:15] if h not in set(core_files))
                if self.mode == "ultra" and scan_result.file_roles:
                    key_roles = {"核心", "引擎", "管线", "服务层", "数据模型", "API", "中间件", "路由"}
                    for path, role in scan_result.file_roles.items():
                        if role in key_roles and path not in set(core_files):
                            core_files.append(path)
                core_contents = _collect_source_files(
                    folder, core_files,
                    max_files=settings.max_files_per_phase,
                    max_size_kb=settings.max_file_size_kb,
                )
                result_text, tokens = analyze_algorithms(
                    phase_results["scan"], phase_results["structure"],
                    core_contents, self.provider,
                    progress_cb=lambda m: self.log.emit(f"  {m}"),
                    mode=self.mode,
                )
                phase_results["algorithm"] = result_text
                Path(os.path.join(output_dir, "analysis", "algorithms.md")).write_text(result_text, encoding="utf-8")
                self.log.emit(f"  ✓ 完成 (tokens: {tokens.get('input_tokens', 0)}+{tokens.get('output_tokens', 0)})")
            except Exception as e:
                self.log.emit(f"  ✗ 失败: {e}")
                continue

            # Phase 4: 生成笔记 (AI)
            if self._cancel:
                break
            self.progress.emit(f"[{project_name}] Phase 4/4: 生成笔记...")
            self.log.emit(f"\n--- Phase 4: 生成笔记 ---")
            try:
                result_text, tokens = generate_notes(
                    phase_results["scan"], phase_results["structure"],
                    phase_results["algorithm"], self.provider,
                    progress_cb=lambda m: self.log.emit(f"  {m}"),
                    mode=self.mode,
                )
                Path(os.path.join(output_dir, "notes", f"{project_name}.md")).write_text(result_text, encoding="utf-8")
                self.log.emit(f"  ✓ 笔记已保存到 output/{project_name}/notes/{project_name}.md")
            except Exception as e:
                self.log.emit(f"  ✗ 失败: {e}")
                continue

            self.log.emit(f"\n✓ {project_name} 蒸馏完成\n")

        self.progress.emit("全部完成")
        self.done.emit()


# ─── 主窗口 ───

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self._theme = self.settings.theme
        self.setWindowTitle("Code-Distiller")
        self.setMinimumSize(820, 620)
        self.resize(1100, 750)
        self.setStyleSheet(build_stylesheet(self._theme))
        self._worker: _AnalysisWorker = None

        self._build_ui()

    # ─── 主题切换 ───

    def _toggle_theme(self):
        self._theme = "dark" if self._theme == "light" else "light"
        self.settings.theme = self._theme
        save_settings(self.settings)
        self.setStyleSheet(build_stylesheet(self._theme))
        self.theme_btn.setText("Light" if self._theme == "dark" else "Dark")
        self._force_qt_combobox()

    def _force_qt_combobox(self):
        for combo in self.findChildren(QComboBox):
            combo.setView(QListView())

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec() == 1:
            self.settings = load_settings()
            if self.settings.theme != self._theme:
                self._theme = self.settings.theme
                self.setStyleSheet(build_stylesheet(self._theme))
                self.theme_btn.setText("Light" if self._theme == "dark" else "Dark")
            self._refresh_provider_combo()
            self.chat_widget.set_providers(self.settings.providers)

    # ─── 构建 UI ───

    def _build_ui(self):
        # ─── Toolbar: Settings + Light/Dark ───
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setStyleSheet("border: none; padding: 0 4px;")

        settings_btn = QToolButton()
        settings_btn.setText("Settings")
        settings_btn.clicked.connect(self._open_settings)
        toolbar.addWidget(settings_btn)

        spacer = QWidget()
        spacer.setSizePolicy(
            spacer.sizePolicy().horizontalPolicy().Expanding,
            spacer.sizePolicy().verticalPolicy().Preferred,
        )
        toolbar.addWidget(spacer)

        self.theme_btn = QToolButton()
        self.theme_btn.setText("Light" if self._theme == "dark" else "Dark")
        self.theme_btn.clicked.connect(self._toggle_theme)
        toolbar.addWidget(self.theme_btn)
        self.addToolBar(toolbar)

        # ─── Central ───
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(8)

        # 顶层两 Tab
        self.top_tabs = QTabWidget()
        self.top_tabs.addTab(self._build_batch_tab(), "  批量蒸馏  ")

        from .chat_widget import ChatWidget
        self.chat_widget = ChatWidget()
        self.top_tabs.addTab(self.chat_widget, "  对话  ")
        self.top_tabs.currentChanged.connect(self._on_top_tab_changed)

        layout.addWidget(self.top_tabs, stretch=1)

        # 状态栏
        self._status_label = QLabel("就绪")
        self._status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.statusBar().addPermanentWidget(self._status_label, stretch=1)

        self._refresh_provider_combo()

    # ─── 批量蒸馏 Tab ───

    def _build_batch_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 12, 16, 12)

        # 顶部：输出目录
        top = QHBoxLayout()
        top.addWidget(self._label("输出目录"))
        self.batch_output_edit = QLineEdit()
        self.batch_output_edit.setPlaceholderText("选择输出目录...")
        if self.settings.last_output_dir:
            self.batch_output_edit.setText(self.settings.last_output_dir)
        top.addWidget(self.batch_output_edit, stretch=1)
        btn_out = QPushButton("浏览")
        btn_out.setProperty("class", "secondary")
        btn_out.setFixedWidth(56)
        btn_out.clicked.connect(self._batch_browse_output)
        top.addWidget(btn_out)
        layout.addLayout(top)

        # 中部：左 (项目文件夹列表) + 右 (AI 配置)
        mid = QHBoxLayout()
        mid.setSpacing(12)

        # 左侧：文件夹列表
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(self._label("项目文件夹"))
        self.batch_folder_list = _DropFolderList()
        # 恢复上次路径
        if self.settings.last_project_path:
            self.batch_folder_list.addItem(self.settings.last_project_path)
        left.addWidget(self.batch_folder_list, stretch=1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("添加文件夹")
        btn_add.clicked.connect(self._batch_add_folders)
        btn_remove = QPushButton("移除")
        btn_remove.setProperty("class", "secondary")
        btn_remove.clicked.connect(self._batch_remove_selected)
        btn_clear = QPushButton("清空")
        btn_clear.setProperty("class", "secondary")
        btn_clear.clicked.connect(self._batch_clear_folders)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_remove)
        btn_row.addWidget(btn_clear)
        left.addLayout(btn_row)
        mid.addLayout(left, stretch=3)

        # 右侧：AI Provider 选择
        right = QVBoxLayout()
        right.setSpacing(6)

        model_grid = QGridLayout()
        model_grid.setSpacing(6)
        model_grid.setContentsMargins(0, 0, 0, 0)
        model_grid.setColumnStretch(1, 1)

        model_grid.addWidget(self._label("AI 模型"), 0, 0)
        self.batch_provider_combo = QComboBox()
        model_grid.addWidget(self.batch_provider_combo, 0, 1)

        model_grid.addWidget(self._label("蒸馏模式"), 1, 0)
        self.batch_mode_combo = QComboBox()
        self.batch_mode_combo.addItem("Normal — 标准分析", "normal")
        self.batch_mode_combo.addItem("High — 深入分析", "high")
        self.batch_mode_combo.addItem("Ultra — 极致分析", "ultra")
        # 恢复上次选择
        idx = self.batch_mode_combo.findData(self.settings.analysis_mode)
        if idx >= 0:
            self.batch_mode_combo.setCurrentIndex(idx)
        model_grid.addWidget(self.batch_mode_combo, 1, 1)

        right.addLayout(model_grid)

        # 开始按钮
        btn_run_row = QHBoxLayout()
        self.btn_batch_start = QPushButton("开始蒸馏")
        self.btn_batch_start.clicked.connect(self._batch_start)
        btn_run_row.addWidget(self.btn_batch_start)
        self.btn_batch_cancel = QPushButton("取消")
        self.btn_batch_cancel.setProperty("class", "secondary")
        self.btn_batch_cancel.clicked.connect(self._batch_cancel)
        self.btn_batch_cancel.setVisible(False)
        btn_run_row.addWidget(self.btn_batch_cancel)
        right.addLayout(btn_run_row)

        # 进度
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 0)
        self.batch_progress.setVisible(False)
        right.addWidget(self.batch_progress)

        self.batch_status = QLabel(" ")
        self.batch_status.setProperty("class", "status")
        self.batch_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.batch_status)

        right.addStretch()
        mid.addLayout(right, stretch=2)

        layout.addLayout(mid, stretch=1)

        # 底部：运行日志
        layout.addWidget(self._label("运行日志"))
        self.batch_log = QTextEdit()
        self.batch_log.setReadOnly(True)
        self.batch_log.setPlaceholderText("运行日志...")
        layout.addWidget(self.batch_log, stretch=2)

        return page

    @staticmethod
    def _label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        return lbl

    # ─── Provider 下拉框 ───

    def _refresh_provider_combo(self):
        self.batch_provider_combo.blockSignals(True)
        self.batch_provider_combo.clear()
        for p in self.settings.providers:
            if p.get("api_key"):
                self.batch_provider_combo.addItem(f"{p['name']} ({p['model']})", p)
        self.batch_provider_combo.blockSignals(False)

    def _get_current_provider(self) -> dict:
        idx = self.batch_provider_combo.currentIndex()
        if idx >= 0:
            return self.batch_provider_combo.itemData(idx) or {}
        for p in self.settings.providers:
            if p.get("api_key"):
                return p
        return {}

    # ─── 文件夹操作 ───

    def _batch_add_folders(self):
        paths = QFileDialog.getExistingDirectory(self, "选择项目文件夹")
        if paths:
            existing = [self.batch_folder_list.item(i).text() for i in range(self.batch_folder_list.count())]
            if paths not in existing:
                self.batch_folder_list.addItem(paths)

    def _batch_remove_selected(self):
        for item in self.batch_folder_list.selectedItems():
            self.batch_folder_list.takeItem(self.batch_folder_list.row(item))

    def _batch_clear_folders(self):
        self.batch_folder_list.clear()

    def _batch_browse_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.batch_output_edit.setText(path)
            self.settings.last_output_dir = path
            save_settings(self.settings)

    # ─── 批量蒸馏 ───

    def _batch_start(self):
        folders = [self.batch_folder_list.item(i).text()
                   for i in range(self.batch_folder_list.count())]
        if not folders:
            self.batch_status.setText("请先添加项目文件夹")
            return

        output_dir = self.batch_output_edit.text().strip()
        if not output_dir:
            self.batch_status.setText("请设置输出目录")
            return

        provider = self._get_current_provider()
        if not provider.get("api_key"):
            self.batch_status.setText("请先在 Settings 中配置 AI Provider")
            return

        mode = self.batch_mode_combo.currentData() or "normal"

        # 保存路径
        self.settings.last_project_path = folders[0]
        self.settings.last_output_dir = output_dir
        self.settings.analysis_mode = mode
        save_settings(self.settings)

        mode_names = {"normal": "标准", "high": "深入", "ultra": "极致"}
        self.batch_log.clear()
        self.btn_batch_start.setEnabled(False)
        self.btn_batch_cancel.setVisible(True)
        self.batch_progress.setVisible(True)
        self.batch_status.setText(f"正在蒸馏 ({mode_names.get(mode, mode)})...")

        self._worker = _AnalysisWorker(folders, output_dir, provider, mode=mode)
        self._worker.log.connect(self._on_batch_log)
        self._worker.progress.connect(self._on_batch_progress)
        self._worker.done.connect(self._on_batch_done)
        self._worker.error.connect(self._on_batch_error)
        self._worker.start()

    def _batch_cancel(self):
        if self._worker:
            self._worker._cancel = True
            self.batch_status.setText("正在取消...")

    def _on_batch_log(self, msg: str):
        self.batch_log.append(msg)

    def _on_batch_progress(self, msg: str):
        self._status_label.setText(msg)
        self.batch_status.setText(msg)

    def _on_batch_done(self):
        self.btn_batch_start.setEnabled(True)
        self.btn_batch_cancel.setVisible(False)
        self.batch_progress.setVisible(False)
        self.batch_status.setText("✓ 蒸馏完成")
        self._status_label.setText("就绪")

        # 蒸馏完成后自动创建对话并切换到对话 Tab
        output_dir = self.batch_output_edit.text().strip()
        folders = [self.batch_folder_list.item(i).text()
                   for i in range(self.batch_folder_list.count())]
        if folders and output_dir:
            self.chat_widget.set_providers(self.settings.providers)
            self.chat_widget._provider_config = self._get_current_provider()
            self.chat_widget._current_project_path = folders[0]
            self.chat_widget._current_output_dir = output_dir
            # 自动新建对话（会加载蒸馏笔记作为首条消息）
            self.chat_widget._on_new_chat()
            self.top_tabs.setCurrentIndex(1)  # 切到对话 Tab

    def _on_batch_error(self, msg: str):
        self.batch_log.append(f"\n✗ 错误: {msg}")
        self.btn_batch_start.setEnabled(True)
        self.btn_batch_cancel.setVisible(False)
        self.batch_progress.setVisible(False)
        self.batch_status.setText(f"✗ 失败: {msg}")

    # ─── Tab 切换 ───

    def _on_top_tab_changed(self, index: int):
        if index == 1:  # 对话 Tab
            provider = self._get_current_provider()
            self.chat_widget.set_providers(self.settings.providers)
            self.chat_widget.refresh_session_list(provider)
            output_dir = self.batch_output_edit.text().strip()
            project_path = ""
            if self.batch_folder_list.count() > 0:
                project_path = self.batch_folder_list.item(0).text()
            self.chat_widget.try_load_project(project_path, output_dir)
