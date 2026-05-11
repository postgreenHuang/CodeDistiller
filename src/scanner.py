"""
Code-Distiller 项目扫描模块
Phase 0: 上下文采矿 (README/CHANGELOG/docs + hub检测 + 测试发现)
Phase 1: 增强扫描 (文件树 + 技术栈 + 依赖 + hub + 测试map)
"""

import json
import os
import re
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict, field

from .config import IGNORE_DIRS, LANG_MAP, CONFIG_FILES, FRAMEWORK_KEYWORDS


# ─── 文件/目录名 → 角色推断 ───

_ROLE_KEYWORDS = {
    "router": "路由", "routes": "路由", "urls": "URL配置",
    "models": "数据模型", "model": "数据模型", "entity": "实体", "entities": "实体层",
    "schema": "Schema", "schemas": "Schema层",
    "views": "视图", "view": "视图",
    "controller": "控制器", "controllers": "控制器层",
    "services": "服务层", "service": "服务",
    "middleware": "中间件",
    "serializer": "序列化", "serializers": "序列化层",
    "repository": "数据访问", "repositories": "数据访问层", "dao": "数据访问",
    "config": "配置", "settings": "配置", "constants": "常量", "enums": "枚举",
    "types": "类型定义", "interfaces": "接口", "typings": "类型定义",
    "utils": "工具", "helpers": "辅助", "tools": "工具集",
    "exceptions": "异常", "errors": "错误处理",
    "validators": "验证", "permissions": "权限",
    "auth": "认证", "authentication": "认证", "authorization": "授权",
    "database": "数据库", "db": "数据库",
    "cache": "缓存",
    "tasks": "异步任务", "queue": "队列", "celery": "异步任务",
    "migrations": "迁移", "migration": "迁移",
    "hooks": "钩子", "events": "事件", "signals": "信号",
    "plugins": "插件", "extensions": "扩展",
    "adapters": "适配器", "handlers": "处理器",
    "commands": "命令", "cli": "CLI",
    "api": "API", "endpoints": "端点",
    "forms": "表单", "filters": "过滤",
    "decorators": "装饰器", "mixins": "混入",
    "base": "基类", "core": "核心",
    "engine": "引擎", "pipeline": "管线",
    "workers": "工作进程", "scheduler": "调度",
    "registry": "注册", "store": "状态",
    "state": "状态管理", "actions": "动作",
    "reducers": "Reducer", "mutations": "Mutation",
    "selectors": "选择器", "resolvers": "解析器",
    "parsers": "解析", "loaders": "加载",
    "renderers": "渲染", "templates": "模板",
    "components": "组件", "pages": "页面",
    "layouts": "布局", "widgets": "部件",
    "manager": "管理器", "builder": "构建器",
    "factory": "工厂", "proxy": "代理",
    "wrapper": "包装", "converter": "转换",
    "transformer": "转换", "mapper": "映射",
    "monitor": "监控", "metrics": "指标",
    "logger": "日志", "log": "日志",
    "policies": "策略", "rules": "规则",
    "listeners": "监听", "subscribers": "订阅",
    "dto": "数据传输", "vo": "值对象",
    "seed": "种子数据", "seeds": "种子数据",
    "init": "初始化", "setup": "安装",
    "main": "入口", "app": "应用",
    "index": "索引", "server": "服务端", "client": "客户端",
}


def _infer_file_role(rel_path: str) -> str:
    """从文件路径推断模块角色"""
    parts = Path(rel_path)
    stem = parts.stem.lower()
    clean = stem
    for prefix in ("test_", "spec_", "mock_", "fake_"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
    for suffix in ("_test", "_spec", "_mock", "_impl", "_base", "_mixin"):
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)]
    if clean in _ROLE_KEYWORDS:
        return _ROLE_KEYWORDS[clean]
    for d in reversed([p.lower() for p in parts.parent.parts]):
        if d in _ROLE_KEYWORDS:
            return _ROLE_KEYWORDS[d]
    for part in clean.split("_"):
        if part in _ROLE_KEYWORDS:
            return _ROLE_KEYWORDS[part]
    return ""


def _infer_file_roles(all_files: list[str]) -> dict[str, str]:
    """为所有文件推断角色"""
    return {f: role for f in all_files if (role := _infer_file_role(f))}


@dataclass
class ScanResult:
    project_name: str = ""
    project_path: str = ""
    file_tree: dict = None
    tech_stack: list = None
    frameworks: list = None
    languages: dict = None
    dependencies: dict = None
    code_stats: dict = None
    entry_files: list = None
    config_files: list = None
    # Phase 0: Harness 采矿
    readme_summary: str = ""
    hub_files: list = None        # [{path, score}]
    test_map: list = None         # [{test_file, target_module, test_names}]
    doc_hints: str = ""
    file_roles: dict = None       # {path: inferred_role}

    def __post_init__(self):
        self.file_tree = self.file_tree or {}
        self.tech_stack = self.tech_stack or []
        self.frameworks = self.frameworks or []
        self.languages = self.languages or {}
        self.dependencies = self.dependencies or {}
        self.code_stats = self.code_stats or {}
        self.entry_files = self.entry_files or []
        self.config_files = self.config_files or []
        self.hub_files = self.hub_files or []
        self.test_map = self.test_map or []
        self.file_roles = self.file_roles or {}

    def to_json(self, path: str):
        Path(path).write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def from_json(path: str) -> "ScanResult":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return ScanResult(**{k: v for k, v in data.items() if k in ScanResult.__dataclass_fields__})

    def summary_text(self, mode: str = "normal") -> str:
        """生成供 AI 分析用的文本摘要（缓存友好的稳定格式）"""
        lines = [f"# 项目: {self.project_name}\n"]

        if self.tech_stack:
            lines.append("## 技术栈")
            lines.extend(f"- {t}" for t in self.tech_stack)
            lines.append("")

        if self.frameworks:
            lines.append("## 框架")
            lines.extend(f"- {f}" for f in self.frameworks)
            lines.append("")

        if self.languages:
            lines.append("## 语言分布")
            for lang, info in sorted(self.languages.items(), key=lambda x: x[1].get("lines", 0), reverse=True):
                lines.append(f"- {lang}: {info['files']} 文件, {info['lines']} 行")
            lines.append("")

        if self.code_stats:
            lines.append("## 代码统计")
            lines.append(f"- 总文件数: {self.code_stats.get('total_files', 0)}")
            lines.append(f"- 总代码行数: {self.code_stats.get('total_lines', 0)}")
            lines.append("")

        if self.dependencies:
            lines.append("## 依赖")
            for mgr, deps in self.dependencies.items():
                if deps:
                    lines.append(f"### {mgr}")
                    for d in deps[:30]:
                        lines.append(f"- {d}")
                    if len(deps) > 30:
                        lines.append(f"- ... 等 {len(deps) - 30} 个")
                    lines.append("")

        if self.entry_files:
            lines.append("## 入口文件")
            for f in self.entry_files:
                lines.append(f"- {f}")
            lines.append("")

        if self.hub_files:
            lines.append("## Hub 文件 (被引用最多)")
            for h in self.hub_files[:15]:
                lines.append(f"- {h['path']} (引用次数: {h['score']})")
            lines.append("")

        if self.test_map:
            lines.append("## 测试概览")
            for t in self.test_map[:20]:
                names_preview = ", ".join(t.get("test_names", [])[:5])
                if len(t.get("test_names", [])) > 5:
                    names_preview += f" ... 等 {len(t['test_names'])} 个"
                target = t.get("target_module", "未知")
                lines.append(f"- {t['test_file']} → {target}: {names_preview}")
            lines.append("")

        if self.readme_summary:
            lines.append("## README 摘要")
            lines.append(self.readme_summary[:2000])
            lines.append("")

        if self.doc_hints:
            lines.append("## 文档线索")
            lines.append(self.doc_hints[:1000])
            lines.append("")

        if self.file_roles:
            lines.append("## 文件角色推断")
            # 按角色分组
            role_groups = {}
            for path, role in sorted(self.file_roles.items()):
                role_groups.setdefault(role, []).append(path)
            for role in sorted(role_groups):
                files = role_groups[role]
                lines.append(f"### {role}")
                for f in files[:10]:
                    lines.append(f"- {f}")
                if len(files) > 10:
                    lines.append(f"- ... 等 {len(files)} 个")
            lines.append("")

        if self.config_files:
            lines.append("## 配置文件")
            for f in self.config_files:
                lines.append(f"- {f}")
            lines.append("")

        if self.file_tree:
            lines.append("## 文件树")
            tree_lines = _format_tree(self.file_tree, indent=0, roles=self.file_roles)
            max_tree = {"normal": 200, "high": 500, "ultra": 999999}.get(mode, 200)
            if len(tree_lines) > max_tree:
                tree_lines = tree_lines[:max_tree]
                tree_lines.append(f"  ... (省略 {len(tree_lines) - max_tree} 项)")
            lines.extend(tree_lines)

        return "\n".join(lines)


def scan_project(project_path: str, progress_cb=None) -> ScanResult:
    """扫描项目目录，返回 ScanResult (Phase 0 + Phase 1)"""
    root = Path(project_path)
    if not root.is_dir():
        return ScanResult()

    if progress_cb:
        progress_cb("扫描文件树...")

    file_tree = _scan_file_tree(root)
    all_files = _flatten_files(file_tree, str(root))

    if progress_cb:
        progress_cb("检测技术栈...")

    languages = _detect_languages(all_files)
    tech_stack, frameworks = _detect_frameworks(root, all_files)
    dependencies = _parse_dependencies(root)
    entry_files = _detect_entry_files(root, all_files)
    config_files = _detect_config_files(root)

    if progress_cb:
        progress_cb("统计代码量...")

    code_stats = _calc_code_stats(all_files, languages)

    # Phase 0: Harness 采矿
    if progress_cb:
        progress_cb("Phase 0: 上下文采矿...")

    readme_summary = _mine_readme(root)
    doc_hints = _mine_docs(root)
    hub_files = _detect_hub_files(root, all_files)
    test_map = _discover_tests(root, all_files)
    file_roles = _infer_file_roles(all_files)

    total_files = code_stats.get("total_files", 0)
    total_lines = code_stats.get("total_lines", 0)

    if progress_cb:
        progress_cb(f"扫描完成: {total_files} 文件, {total_lines} 行, "
                    f"{len(hub_files)} hub文件, {len(test_map)} 测试文件")

    return ScanResult(
        project_name=root.name,
        project_path=str(root),
        file_tree=file_tree,
        tech_stack=tech_stack,
        frameworks=frameworks,
        languages=languages,
        dependencies=dependencies,
        code_stats=code_stats,
        entry_files=entry_files,
        config_files=config_files,
        readme_summary=readme_summary,
        hub_files=hub_files,
        test_map=test_map,
        doc_hints=doc_hints,
        file_roles=file_roles,
    )


# ─── Phase 0: 上下文采矿 ───

_DOC_FILES = ["README.md", "README.MD", "README", "README.txt",
              "CHANGELOG.md", "CHANGELOG", "HISTORY.md",
              "CONTRIBUTING.md", "ARCHITECTURE.md", "DESIGN.md"]


def _mine_readme(root: Path) -> str:
    """解析 README 等项目文档，提取架构线索"""
    parts = []

    for name in _DOC_FILES:
        f = root / name
        if f.exists():
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                # 截取前 3000 字符（避免太大）
                truncated = content[:3000]
                if len(content) > 3000:
                    truncated += "\n... (已截断)"
                parts.append(f"### {name}\n{truncated}")
            except Exception:
                pass

    # 也检查 docs/ 目录中的 md 文件
    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for f in sorted(docs_dir.glob("*.md"))[:5]:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")[:1500]
                parts.append(f"### docs/{f.name}\n{content}")
            except Exception:
                pass

    return "\n\n".join(parts)


def _mine_docs(root: Path) -> str:
    """从文档中提取架构相关的关键句子"""
    hints = []
    arch_keywords = [
        "架构", "architecture", "设计", "design", "模块", "module",
        "组件", "component", "分层", "layer", "插件", "plugin",
        "微服务", "microservice", "MVC", "MVVM", "管道", "pipeline",
        "核心", "core", "引擎", "engine", "框架", "framework",
        "入口", "entry", "配置", "config", "部署", "deploy",
    ]

    checked = set()
    for name in _DOC_FILES:
        f = root / name
        if f.exists() and f.name not in checked:
            checked.add(f.name)
            try:
                _extract_arch_hints(f, arch_keywords, hints)
            except Exception:
                pass

    return "\n".join(hints[:30])


def _extract_arch_hints(f: Path, keywords: list, hints: list):
    """从单个文件中提取包含架构关键词的句子"""
    content = f.read_text(encoding="utf-8", errors="ignore")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if any(kw.lower() in lower for kw in keywords):
            if len(line) < 300:
                hints.append(f"- [{f.name}] {line}")


def _detect_hub_files(root: Path, all_files: list[str]) -> list[dict]:
    """分析 import 关系，计算 hub 分数（被引用次数）"""
    import_counter = defaultdict(int)

    _IMPORT_PATTERNS = [
        # Python: from X import Y / import X
        re.compile(r'^\s*(?:from|import)\s+([a-zA-Z_][\w.]*)', re.MULTILINE),
        # JS/TS: import ... from 'X' / require('X')
        re.compile(r'''(?:import\s+.*?\s+from\s+['"](\.[^'"]+)['"]|require\s*\(\s*['"](\.[^'"]+)['"])'''),
        # Go: import "X"
        re.compile(r'^\s*"([^"]+)"', re.MULTILINE),
        # Rust: use X::Y
        re.compile(r'^\s*use\s+([a-zA-Z_][\w:]*)', re.MULTILINE),
        # Java: import X.Y.Z
        re.compile(r'^\s*import\s+([a-zA-Z_][\w.]*)', re.MULTILINE),
    ]

    code_exts = set(LANG_MAP.keys())
    project_name = root.name

    for rel_path in all_files:
        ext = Path(rel_path).suffix.lower()
        if ext not in code_exts:
            continue
        full_path = root / rel_path
        try:
            size = full_path.stat().st_size
            if size > 200000:  # 跳过 >200KB 的文件
                continue
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for pattern in _IMPORT_PATTERNS:
            for m in pattern.finditer(content):
                import_path = m.group(1) or m.group(2) if m.lastindex and m.group(m.lastindex) else ""
                if not import_path:
                    continue

                # 尝试将 import 路径解析为项目内文件
                resolved = _resolve_import(import_path, root, project_name, ext)
                if resolved:
                    import_counter[resolved] += 1

    # 排序取 top hub 文件
    sorted_hubs = sorted(import_counter.items(), key=lambda x: x[1], reverse=True)
    return [{"path": p, "score": s} for p, s in sorted_hubs[:30]]


def _resolve_import(import_path: str, root: Path, project_name: str, from_ext: str) -> str:
    """将 import 路径解析为项目内相对路径"""
    # Python: src.foo.bar → src/foo/bar.py 或 src/foo/bar/__init__.py
    if from_ext == ".py":
        parts = import_path.split(".")
        # 去掉项目名前缀
        if parts and parts[0] == project_name:
            parts = parts[1:]
        if not parts:
            return ""
        rel = "/".join(parts)
        # 尝试 .py 文件
        if (root / f"{rel}.py").exists():
            return f"{rel}.py"
        # 尝试包目录
        if (root / rel / "__init__.py").exists():
            return f"{rel}/__init__.py"

    # JS/TS: ./foo or ../bar → resolve relative path
    if from_ext in (".js", ".ts", ".tsx", ".jsx", ".mjs"):
        if import_path.startswith("."):
            rel = import_path.lstrip("./")
            for ext in ("", ".js", ".ts", ".tsx", "/index.js", "/index.ts"):
                if (root / f"{rel}{ext}").exists():
                    return f"{rel}{ext}"

    return ""


def _discover_tests(root: Path, all_files: list[str]) -> list[dict]:
    """发现测试文件，提取测试名作为 API 描述"""
    test_files = []
    test_patterns = [
        re.compile(r'^test_', re.IGNORECASE),
        re.compile(r'_test\.', re.IGNORECASE),
        re.compile(r'\.test\.', re.IGNORECASE),
        re.compile(r'\.spec\.', re.IGNORECASE),
        re.compile(r'^tests?/', re.IGNORECASE),
    ]

    for rel_path in all_files:
        name = Path(rel_path).name
        is_test = any(p.search(name) for p in test_patterns)
        # 也检查 tests/ 目录下的文件
        if not is_test and "/test" in rel_path.lower():
            is_test = True
        if not is_test:
            continue

        full_path = root / rel_path
        try:
            size = full_path.stat().st_size
            if size > 100000:
                continue
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        test_names = _extract_test_names(content, Path(rel_path).suffix.lower())
        target = _guess_test_target(rel_path)

        test_files.append({
            "test_file": rel_path,
            "target_module": target,
            "test_names": test_names[:20],
        })

    return test_files


def _extract_test_names(content: str, ext: str) -> list[str]:
    """从测试文件中提取测试函数/用例名"""
    names = []

    if ext == ".py":
        # Python: def test_xxx() / class TestXxx
        for m in re.finditer(r'(?:def\s+(test_\w+)|class\s+(Test\w+))', content):
            name = m.group(1) or m.group(2)
            if name:
                # 将 test_xxx_yyy 转为可读形式
                readable = name.replace("test_", "").replace("_", " ").strip()
                names.append(readable if readable else name)

    elif ext in (".js", ".ts", ".tsx", ".jsx", ".mjs"):
        # JS/TS: describe("xxx", ...) / it("xxx", ...) / test("xxx", ...)
        for m in re.finditer(r'(?:describe|it|test)\s*\(\s*["\']([^"\']+)', content):
            names.append(m.group(1))

    elif ext == ".go":
        # Go: func TestXxx(t *testing.T)
        for m in re.finditer(r'func\s+(Test\w+)', content):
            name = m.group(1).replace("Test", "")
            # CamelCase → space separated
            readable = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
            names.append(readable)

    elif ext == ".rs":
        # Rust: #[test] fn test_xxx()
        for m in re.finditer(r'fn\s+(\w+)\s*\(', content):
            if "test" in content[max(0, m.start() - 50):m.start()].lower():
                names.append(m.group(1))

    elif ext == ".java":
        # Java: @Test void testXxx()
        for m in re.finditer(r'(?:@Test\s+(?:public\s+)?void\s+(\w+))', content):
            names.append(m.group(1))

    return names


def _guess_test_target(test_path: str) -> str:
    """从测试文件路径猜测被测模块"""
    name = Path(test_path).stem
    # test_foo.py → foo.py, foo.test.ts → foo.ts
    for prefix in ("test_", "test-"):
        if name.startswith(prefix):
            return name[len(prefix):]
    for suffix in ("_test", ".test", ".spec", "_spec"):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    # 从路径猜测: tests/test_app.py → app, __tests__/app.test.ts → app
    parts = Path(test_path).parts
    if len(parts) > 1:
        return parts[-2]
    return name


# ─── 文件树扫描 ───

def _should_ignore(name: str) -> bool:
    if name in IGNORE_DIRS:
        return True
    if name.startswith(".") and name not in (".github", ".env.example"):
        return True
    return False


def _scan_file_tree(root: Path, max_depth: int = 6) -> dict:
    result = {"name": root.name, "type": "dir", "children": []}
    try:
        entries = sorted(root.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
    except PermissionError:
        return result

    for entry in entries:
        if _should_ignore(entry.name):
            continue
        if entry.is_dir():
            if max_depth > 0:
                child = _scan_file_tree(entry, max_depth - 1)
                child_count = _count_children(child)
                if child_count > 0:
                    result["children"].append(child)
        else:
            result["children"].append({
                "name": entry.name,
                "type": "file",
                "size": entry.stat().st_size,
            })

    return result


def _count_children(node: dict) -> int:
    if node["type"] == "file":
        return 1
    return sum(_count_children(c) for c in node.get("children", []))


def _flatten_files(tree: dict, root_path: str, prefix: str = "") -> list[str]:
    files = []
    for child in tree.get("children", []):
        path = f"{prefix}/{child['name']}" if prefix else child["name"]
        if child["type"] == "file":
            files.append(path)
        else:
            files.extend(_flatten_files(child, root_path, path))
    return files


def _format_tree(tree: dict, indent: int = 0, roles: dict = None) -> list[str]:
    lines = []
    prefix = "  " * indent
    if tree["type"] == "dir":
        child_count = len(tree.get("children", []))
        dir_role = (roles or {}).get(tree.get("name", ""), "")
        role_tag = f" [{dir_role}]" if dir_role else ""
        lines.append(f"{prefix}{tree['name']}/ ({child_count} items){role_tag}")
        for child in tree.get("children", []):
            lines.extend(_format_tree(child, indent + 1, roles))
    else:
        size_kb = tree.get("size", 0) / 1024
        file_role = (roles or {}).get(tree.get("name", ""), "")
        role_tag = f" [{file_role}]" if file_role else ""
        if size_kb > 100:
            lines.append(f"{prefix}{tree['name']} ({size_kb:.0f}KB){role_tag}")
        else:
            lines.append(f"{prefix}{tree['name']}{role_tag}")
    return lines


# ─── 语言检测 ───

def _detect_languages(all_files: list[str]) -> dict:
    lang_data = defaultdict(lambda: {"files": 0, "lines": 0})
    for f in all_files:
        ext = Path(f).suffix.lower()
        lang = LANG_MAP.get(ext)
        if lang:
            lang_data[lang]["files"] += 1
    return dict(lang_data)


def _count_lines(file_path: str) -> int:
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


# ─── 框架检测 ───

def _detect_frameworks(root: Path, all_files: list[str]) -> tuple[list, list]:
    tech_stack = []
    frameworks = []

    for cfg_name, tool in CONFIG_FILES.items():
        if (root / cfg_name).exists():
            tech_stack.append(tool)

    for source_file, source_name in [
        (root / "package.json", None),
        (root / "requirements.txt", None),
        (root / "pyproject.toml", None),
    ]:
        if not source_file.exists():
            continue
        try:
            content = source_file.read_text(encoding="utf-8").lower()
            if source_file.name == "package.json":
                data = json.loads(content)
                content = " ".join(
                    list(data.get("dependencies", {}).keys()) +
                    list(data.get("devDependencies", {}).keys())
                )
            for keyword, framework in FRAMEWORK_KEYWORDS.items():
                if keyword in content and framework not in frameworks:
                    frameworks.append(framework)
        except Exception:
            pass

    return tech_stack, frameworks


# ─── 依赖解析 ───

def _parse_dependencies(root: Path) -> dict:
    deps = {}

    pkg_json = root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            items = [f"{k}: {v}" for k, v in {
                **data.get("dependencies", {}), **data.get("devDependencies", {})
            }.items()]
            if items:
                deps["npm"] = items
        except Exception:
            pass

    req_file = root / "requirements.txt"
    if req_file.exists():
        try:
            lines = [l.strip() for l in req_file.read_text(encoding="utf-8").splitlines()
                     if l.strip() and not l.startswith("#")]
            if lines:
                deps["pip"] = lines
        except Exception:
            pass

    cargo = root / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text(encoding="utf-8")
            in_deps = False
            items = []
            for line in content.splitlines():
                if line.strip() == "[dependencies]":
                    in_deps = True
                    continue
                if line.startswith("[") and in_deps:
                    break
                if in_deps and "=" in line:
                    items.append(line.strip())
            if items:
                deps["cargo"] = items
        except Exception:
            pass

    go_mod = root / "go.mod"
    if go_mod.exists():
        try:
            content = go_mod.read_text(encoding="utf-8")
            requires = []
            in_require = False
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("require ("):
                    in_require = True
                    continue
                if stripped == ")" and in_require:
                    in_require = False
                    continue
                if in_require and stripped and not stripped.startswith("//"):
                    requires.append(stripped)
                elif stripped.startswith("require ") and "(" not in stripped:
                    requires.append(stripped.replace("require ", ""))
            if requires:
                deps["go"] = requires
        except Exception:
            pass

    return deps


# ─── 入口文件检测 ───

_ENTRY_FILE_NAMES = {
    "main.py", "app.py", "manage.py", "wsgi.py", "asgi.py",
    "index.js", "index.ts", "index.mjs", "app.js", "app.ts",
    "main.js", "main.ts", "server.js", "server.ts",
    "main.go", "main.rs", "lib.rs",
    "Main.java", "Application.java", "App.java",
    "Program.cs", "Startup.cs",
    "main.rb", "config.ru", "index.php", "main.swift",
    "main.c", "main.cpp",
}

_ENTRY_DIR_NAMES = {"src", "cmd", "cmd/server", "app", "bin"}


def _detect_entry_files(root: Path, all_files: list[str]) -> list[str]:
    entries = []
    candidates = [root]
    for d in _ENTRY_DIR_NAMES:
        sub = root / d
        if sub.is_dir():
            candidates.append(sub)

    for candidate in candidates:
        for name in _ENTRY_FILE_NAMES:
            f = candidate / name
            if f.exists():
                rel = f.relative_to(root)
                if str(rel) not in entries:
                    entries.append(str(rel))
    return entries[:10]


def _detect_config_files(root: Path) -> list[str]:
    found = []
    for cfg_name in CONFIG_FILES:
        if (root / cfg_name).exists():
            found.append(cfg_name)
    for extra in (".env", ".env.example", ".env.local", "config.json",
                  "config.yaml", "config.yml", "config.toml",
                  ".eslintrc.js", ".eslintrc.json", "tsconfig.json",
                  "vite.config.ts", "vite.config.js", "webpack.config.js",
                  "docker-compose.yml", "docker-compose.yaml",
                  ".gitignore", ".dockerignore"):
        if (root / extra).exists():
            found.append(extra)
    return found


# ─── 代码统计 ───

def _calc_code_stats(all_files: list[str], languages: dict) -> dict:
    total_lines = 0
    counted_files = 0
    code_exts = set(LANG_MAP.keys())

    for f in all_files:
        ext = Path(f).suffix.lower()
        if ext in code_exts:
            lang = LANG_MAP[ext]
            try:
                lines = _count_lines(f)
                languages[lang]["lines"] += lines
                total_lines += lines
                counted_files += 1
            except Exception:
                pass

    return {
        "total_files": len(all_files),
        "code_files": counted_files,
        "total_lines": total_lines,
    }
