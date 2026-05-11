"""
Code-Distiller 配置管理
- 用户配置持久化到 settings.json
- 支持多 AI Provider、自定义快捷提问
"""

import json
from pathlib import Path
from dataclasses import dataclass, field, asdict

USER_DATA_DIR = Path.home() / ".Code-Distiller"
USER_DATA_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = USER_DATA_DIR / "settings.json"

# 需要忽略的目录（扫描时跳过）
IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", ".next", ".nuxt", "target",
    "bin", "obj", ".gradle", ".mvn", "coverage", ".pytest_cache",
    ".mypy_cache", ".tox", ".eggs", "eggs", "*.egg-info",
    "vendor", "Pods", ".bundle", ".cache", ".local",
}

# 文件扩展名 → 语言
LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript (React)", ".jsx": "JavaScript (React)",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".c": "C",
    ".h": "C/C++ Header", ".hpp": "C++ Header",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP",
    ".swift": "Swift", ".m": "Objective-C",
    ".scala": "Scala", ".clj": "Clojure",
    ".lua": "Lua", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".ps1": "PowerShell", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".vue": "Vue", ".svelte": "Svelte", ".dart": "Dart",
    ".zig": "Zig", ".nim": "Nim", ".ex": "Elixir", ".exs": "Elixir",
    ".hs": "Haskell", ".ml": "OCaml",
    ".proto": "Protocol Buffers", ".thrift": "Thrift",
}

# 配置文件 → 框架/工具标识
CONFIG_FILES = {
    "package.json": "Node.js",
    "requirements.txt": "Python",
    "Pipfile": "Python (Pipenv)",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "build.gradle.kts": "Kotlin (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "pubspec.yaml": "Dart/Flutter",
    "mix.exs": "Elixir",
    "Package.swift": "Swift",
    "CMakeLists.txt": "CMake",
    "Makefile": "Make",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
}

# 框架检测关键词（在 package.json / requirements.txt 中搜索）
FRAMEWORK_KEYWORDS = {
    "react": "React", "vue": "Vue", "next": "Next.js", "nuxt": "Nuxt",
    "angular": "Angular", "svelte": "Svelte", "express": "Express",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "keras": "Keras",
    "scikit-learn": "scikit-learn", "numpy": "NumPy", "pandas": "Pandas",
    "spring": "Spring", "rails": "Ruby on Rails", "gin": "Gin",
    "actix": "Actix", "rocket": "Rocket",
    "pydantic": "Pydantic", "sqlalchemy": "SQLAlchemy", "alembic": "Alembic",
    "pytest": "pytest", "jest": "Jest", "vitest": "Vitest",
    "webpack": "Webpack", "vite": "Vite", "rollup": "Rollup",
    "tailwindcss": "Tailwind CSS", "bootstrap": "Bootstrap",
    "electron": "Electron", "tauri": "Tauri", "pyside6": "PySide6",
    "qt": "Qt", "unity": "Unity", "unreal": "Unreal Engine",
}


@dataclass
class Settings:
    last_project_path: str = ""
    last_output_dir: str = ""
    chat_font_family: str = ""
    chat_font_scale: int = 100
    theme: str = "dark"
    max_file_size_kb: int = 512  # 超过此大小的文件跳过内容读取
    max_files_per_phase: int = 30  # 每个分析阶段最多读取的文件数
    analysis_mode: str = "normal"  # normal / high / ultra
    providers: list = field(default_factory=lambda: [
        {"name": "Gemini", "base_url": "", "api_key": "", "model": "gemini-2.5-pro"},
        {"name": "OpenAI", "base_url": "", "api_key": "", "model": "gpt-4o"},
        {"name": "Claude", "base_url": "", "api_key": "", "model": "claude-sonnet-4-6"},
        {"name": "Ollama", "base_url": "http://localhost:11434", "api_key": "", "model": "llama3"},
    ])
    quick_questions: list = field(default_factory=lambda: [
        {"name": "解释架构", "text": "请用通俗的语言解释这个项目的整体架构"},
        {"name": "核心算法", "text": "请详细说明这个项目中的核心算法和数据结构"},
        {"name": "依赖关系", "text": "请梳理主要模块之间的调用关系和数据流"},
        {"name": "学习路径", "text": "如果要深入理解这个项目，建议按什么顺序阅读代码？"},
        {"name": "设计模式", "text": "这个项目用到了哪些设计模式？分别在哪里体现？"},
    ])
    default_analysis_prompt: str = (
        "你是一位资深代码架构师。我会给你提供一个代码项目的扫描结果和关键源码。\n"
        "请生成一份面向开发者的结构化项目分析报告，严格按以下层次输出：\n\n"
        "## 项目概览\n"
        "用一段话概括项目用途和核心价值。\n\n"
        "## 技术栈\n"
        "语言、框架、关键依赖及版本。\n\n"
        "## 项目结构\n"
        "目录树 + 每个顶级目录的职责说明。\n\n"
        "## 架构设计\n"
        "模块划分、设计模式、数据流向、关键接口。\n\n"
        "## 依赖关系\n"
        "核心第三方库及其用途。\n\n"
        "## 核心算法\n"
        "按模块列出关键算法、数据结构、复杂度分析。\n\n"
        "## 入口与启动流程\n"
        "从入口文件到核心逻辑的调用链路。\n\n"
        "## 配置体系\n"
        "配置文件、环境变量、默认值。\n\n"
        "## 学习路径\n"
        "建议的阅读顺序和理解路径。\n"
    )


def load_settings() -> Settings:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return Settings(**{k: v for k, v in data.items() if k in Settings.__dataclass_fields__})
        except Exception:
            pass
    s = Settings()
    save_settings(s)
    return s


def save_settings(s: Settings):
    SETTINGS_FILE.write_text(
        json.dumps(asdict(s), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_project_output_dir(output_dir: str, project_path: str) -> Path:
    from pathlib import PurePosixPath
    name = Path(project_path).name
    project_dir = Path(output_dir) / name
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("scan", "analysis", "notes", "chat"):
        (project_dir / sub).mkdir(exist_ok=True)
    return project_dir
