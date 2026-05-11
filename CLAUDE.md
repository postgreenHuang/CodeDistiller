# Code-Distiller — 代码工程蒸馏器

将代码工程蒸馏为结构化技术文档，支持与"咀嚼了工程知识"的 AI 导师持续对话。
目标是帮助开发者**快速掌握一个陌生代码工程的框架、技术栈、设计、依赖和重点算法**。

面向开发者，本地桌面 GUI 应用，可打包为 .exe。

## 技术栈

- Python 3.10+ / PySide6（Qt6）/ PyInstaller
- OpenAI 兼容 API（云端 AI，支持 Gemini/Claude/OpenAI/Ollama）
- settings.json 持久化配置

## 项目结构

```
CodeDistiller/
├── src/
│   ├── config.py           # 配置管理 (settings.json)
│   ├── scanner.py          # ① 项目扫描 (Phase 0 采矿 + Phase 1 增强扫描)
│   ├── analyzer.py         # ② 代码分析 (Phase 2 结构 + Phase 3 算法 + Phase 4 笔记)
│   ├── chat.py             # ③ AI 对话 (agent loop + 三层上下文管理)
│   ├── session_io.py       # ④ 对话导出/导入 (.cdc ZIP)
│   └── gui/
│       ├── app.py          # 主窗口 (两 Tab: 批量蒸馏 + 对话)
│       ├── chat_widget.py  # AI 对话界面 (session树 + 消息气泡 + agent状态)
│       ├── theme.py        # Light/Dark 主题 QSS
│       └── settings_dialog.py
├── output/{project_name}/
│   ├── scan/               # 扫描结果 (scan_result.json)
│   ├── analysis/           # 分析结果 (structure.md, algorithms.md)
│   └── notes/              # 蒸馏笔记 ({project_name}.md)
├── main.py                 # 入口
└── requirements.txt
```

## 核心设计：渐进式分析 + 缓存命中优化

### 设计理念

模拟高级架构师分析陌生项目的思维过程：先本地采矿建立全局认知，
再逐阶段 AI 分析，每阶段只发送增量内容，前阶段 prompt 作为 system prefix 被缓存命中。

### 分析管线（4 阶段，三档模式）

支持 Normal / High / Ultra 三档蒸馏模式，影响文件读取量、prompt 深度和 max_tokens。

```
Phase 1: 增强扫描 (本地, 0 token)
  = 上下文采矿 + 文件树 + 技术栈 + 依赖 + 代码统计
  采矿内容包括:
    ├── README/CHANGELOG/docs 解析，提取架构线索
    ├── import 分析，计算文件 hub 分数
    ├── 测试文件发现，提取测试名作为 API 描述
    ├── 入口文件 + 配置文件检测
    └── 文件名角色推断 (80+ 关键词: router→路由, models→数据模型...)
  → scan_summary (含 hub_files, test_map, doc_hints, file_roles)
  → 保存到 output/{project}/scan/scan_result.json
       ↓
Phase 2: 结构分析 (AI)
  normal: 入口+配置文件 (max 15), 8k tokens
  high:   入口+hub+配置 (max 30), 8k tokens, 增强prompt
  ultra:  入口+hub+配置+角色关键文件 (max 50), 16k tokens, 极致prompt
  AI 输出: 入口流程 / 模块划分 / 设计模式 / 数据流 / 建议深挖文件
  → structure.md
       ↓
Phase 3: 算法深挖 (AI, 增量)
  normal: Phase 2 建议文件 (max 30), 8k tokens
  high:   + hub文件 (max 50), 8k tokens, 增强prompt
  ultra:  + hub+角色关键文件 (max 100), 16k tokens, 极致prompt
  AI 输出: 核心算法 / 数据结构 / 性能热点 / 设计亮点
  → algorithms.md
       ↓
Phase 4: 笔记生成 (AI, 增量)
  normal: 基础模板, 8k tokens
  high:   + 模块详解/数据流图/设计决策, 8k tokens
  ultra:  + 完整API参考/并发安全/反模式/测试覆盖, 16k tokens
  → {project_name}.md
```

### 缓存命中链

```
Phase 2 system = Phase 1 scan_result                    ← 首次写入缓存
Phase 3 system = Phase 1 scan_result + Phase 2 结果     ← Phase 1 部分命中缓存
Phase 4 system = Phase 1 + Phase 2 + Phase 3 结果       ← Phase 1+2 部分命中缓存
对话 system   = 蒸馏笔记 + 关键源码                      ← 整段缓存
```

### Phase 1：增强扫描（本地，0 token）

本地预处理，为 AI 提供高质量线索，0 token 消耗：
- **文件树扫描**：递归目录结构（忽略 node_modules/.git 等）
- **技术栈检测**：语言分布 + 框架识别（通过 package.json/requirements.txt 等关键词）
- **依赖解析**：npm/pip/cargo/go 多包管理器支持
- **代码统计**：总文件数、总代码行数、各语言分布
- **README 采矿**：解析 README.md / CHANGELOG.md / docs/，提取架构描述
- **Hub 文件检测**：分析 import/require，计算被引用次数，识别核心模块
- **测试发现**：扫描测试文件，提取测试函数名作为 API 文档
- **入口文件检测**：识别 main.py / index.js / main.go 等入口
- **配置文件检测**：识别 Dockerfile / tsconfig / .env 等
- **文件角色推断**：80+ 关键词匹配（router→路由, models→数据模型, middleware→中间件...），
  按角色分组输出，帮助 AI 快速理解每个文件的职责

### Phase 2-4：三档模式差异

| 维度 | Normal | High | Ultra |
|------|--------|------|-------|
| Phase 2 文件数 | 15 | 30 | 50 |
| Phase 3 文件数 | 30 | 50 | 100 |
| max_tokens | 8192 | 8192 | 16384 |
| 结构分析 | 基础 | +模块证据/数据流/接口契约/错误处理 | +依赖图/API签名/并发模型/反模式/安全性 |
| 算法分析 | 基础 | +代码位置/边界条件/内存模式 | +伪代码对比/性能估算/数据流生命周期 |
| 笔记输出 | 基础模板 | +模块详解/数据流图/设计决策 | +完整API参考/并发安全/反模式/测试覆盖 |

## 对话系统

### Agent Loop

AI 可通过 `[READ: 文件路径]` 自主请求读取项目源文件（最多 4 轮，每轮最多 5 个文件）。

**文件读取流程**：
1. AI 回复中包含 `[READ: src/scanner.py]`
2. 系统解析路径，相对于 project_path 解析为绝对路径
3. 读取文件内容（单文件上限 30000 字符，总量上限 120000 字符）
4. 将内容注入上下文，AI 继续回答
5. **路径纠错**：如果文件找不到，系统将项目实际文件列表反馈给 AI，
   让 AI 用正确路径重试，而非直接放弃

### 三层上下文管理

- **压缩摘要**：对话过长时自动压缩旧消息（token 预算 80% 触发）
- **最近对话**：至少保留最近 6 条消息
- **按需读取**：agent loop 中读取的文件内容作为额外上下文

### 对话管理

- **Session 持久化**：`~/.Code-Distiller/sessions/{session_id}/chat_history.json`
- **文件夹分组**：用户自建文件夹（`~/.Code-Distiller/folders.json`），右键对话"移动到"
- **隐藏对话**：右键"隐藏"/"取消隐藏"，顶部 👁 按钮切换显示
- **拖拽排序**：同文件夹内拖拽调整顺序，持久化 order 字段
- **重命名**：双击对话项
- **导出/导入**：`.cdc` ZIP 格式（含 chat_history + 关联笔记），导入时自动生成新 session ID
- **删除**：右键删除（支持多选批量删除）

### 对话 System Prompt

```
你是一位资深代码架构导师。你刚刚带领学生分析了一个代码工程。
以下是工程的蒸馏笔记和关键源码片段，作为你的知识基础：

--- 蒸馏笔记 ---
{notes}

--- 关键源码 ---
{source}

你的任务是：
1. 回答关于代码架构、设计决策的问题
2. 解释核心算法和数据结构的原理
3. 帮助建立模块之间的关联理解
4. 指出容易忽略的重要细节和潜在问题
5. 建议深入阅读的方向

--- 文件读取能力 ---
当你需要查看项目源文件来准确回答问题时，你可以插入 [READ: 文件路径] 请求读取。
系统会读取文件并提供内容。如果路径不对，系统会返回项目文件列表供你纠正。
读取后基于实际代码给出准确回答。
```

## GUI 设计

布局完全对齐 Video-Distiller 风格：
- 顶部 Toolbar: Settings + Light/Dark 切换
- 批量蒸馏 Tab: 左(文件夹列表+拖拽) + 右(AI模型+蒸馏模式+开始) + 底部(运行日志)
- 对话 Tab: 左(session树+搜索+📁新建文件夹+👁显示隐藏) + 右(消息气泡+输入框+齿轮配置)

批量蒸馏一键执行 4 阶段管线，运行日志实时输出各阶段进度。
Phase 1 本地秒级完成，Phase 2-4 逐阶段调用 AI。

蒸馏完成自动创建对话并切换到对话 Tab，加载蒸馏笔记作为首条消息。

## 快捷提问默认模板

- "解释架构" → 请用通俗的语言解释这个项目的整体架构
- "核心算法" → 请详细说明这个项目中的核心算法和数据结构
- "依赖关系" → 请梳理主要模块之间的调用关系和数据流
- "学习路径" → 如果要深入理解这个项目，建议按什么顺序阅读代码？
- "设计模式" → 这个项目用到了哪些设计模式？分别在哪里体现？

## 输出笔记模板

```markdown
## 项目概览
一段话概括项目用途和核心价值。

## 技术栈
语言、框架、关键依赖及版本。

## 项目结构
目录树 + 每个顶级目录的职责说明。

## 架构设计
模块划分、设计模式、数据流向、关键接口。

## 依赖关系
核心第三方库及其用途。

## 核心算法
按模块列出关键算法、数据结构、复杂度分析。

## 入口与启动流程
从入口文件到核心逻辑的调用链路。

## 配置体系
配置文件、环境变量、默认值。

## 学习路径
建议的阅读顺序和理解路径。
```

## 开发约定

- 复用 Video-Distiller 的 GUI 组件和主题系统（theme.py / chat_widget.py）
- 模块通过文件系统解耦，输入输出均为文件路径
- 非破坏性分析：不修改源项目任何文件
- AI 调用遵循渐进式策略，最大化缓存命中
- 输出按项目名组织，支持多个项目并行分析
- GUI：PySide6 + Apple 风格 QSS，Light/Dark 主题
- 改 GUI 必须验证 dark 模式覆盖完整
- 配置字段变更需兼容旧 settings.json

## 数据存储

```
~/.Code-Distiller/
├── settings.json              # 全局配置 (主题/Provider/快捷提问/分析模式)
├── folders.json               # 用户自建对话文件夹
└── sessions/
    ├── 20260511_143000/       # session by 时间戳
    │   ├── chat_history.json  # 对话历史 + 元数据
    │   └── notes.md           # 导入时嵌入的笔记
    └── ...

output/{project_name}/
├── scan/
│   └── scan_result.json       # 完整扫描结果 (JSON)
├── analysis/
│   ├── structure.md           # Phase 2 结构分析
│   └── algorithms.md          # Phase 3 算法深挖
└── notes/
    └── {project_name}.md      # Phase 4 蒸馏笔记
```

## 依赖

```
PySide6>=6.5, python-dotenv, google-generativeai, openai, anthropic,
requests, Pillow, pyinstaller
```

不需要 FFmpeg / OpenCV / Whisper 等多媒体依赖。

## 当前硬件

i9-11代 / 64GB RAM / NVIDIA RTX 3090 24GB VRAM
- Ollama 可用 CUDA 加速本地模型
- AI 分析主要用云端 API（Gemini / Claude / OpenAI）
