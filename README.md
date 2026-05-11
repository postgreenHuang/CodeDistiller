<h1 align="center">Code Distiller</h1>
<p align="center"><strong>像高级架构师一样读懂任何代码工程</strong></p>
<p align="center">
把陌生代码工程蒸馏成结构化技术文档，然后和一位"已经读完整个项目"的 AI 导师持续对话。
</p>
<img width="1028" height="777" alt="图片" src="https://github.com/user-attachments/assets/a3abbd5e-5c36-42c3-88a8-7c44509435ca" />
<img width="1033" height="778" alt="图片" src="https://github.com/user-attachments/assets/ebdc3cf5-dae4-4606-8d28-8381fbecbc4b" />


<br>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/PySide6-Qt6-41CD52?style=flat&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/AI-Gemini%20%7C%20Claude%20%7C%20OpenAI%20%7C%20Ollama-blueviolet?style=flat" />
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-lightgrey?style=flat" />
</p>

<br>

---

## 30 秒了解它做了什么

```
你接手了一个 200+ 文件的陌生项目，文档过时，代码如迷宫。

传统方式：  花几天读代码 → 猜架构 → 问同事 → 再猜
Code Distiller：拖入文件夹 → 点"开始蒸馏" → 喝杯咖啡 → 拿到完整架构笔记

然后问 AI："解释一下路由层的实现"，它直接给你画数据流图。
```

## 核心功能

### 渐进式 4 阶段分析管线

不是一次把代码丢给 AI 猜，而是模拟高级架构师的思维过程：

| 阶段 | 做什么 | 怎么做 |
|------|--------|--------|
| **Phase 1** 增强扫描 | 文件树、技术栈、依赖、代码统计 | 本地秒级完成，0 token |
| **Phase 2** 结构分析 | 模块划分、设计模式、数据流、关键接口 | AI 分析入口+核心文件 |
| **Phase 3** 算法深挖 | 核心算法、数据结构、性能热点 | AI 定向分析核心源码 |
| **Phase 4** 笔记生成 | 完整结构化技术文档 | AI 综合所有阶段输出 |

每阶段只发送增量内容，前阶段作为缓存前缀复用，降低 token 成本。

### 三档蒸馏模式

| | Normal | High | Ultra |
|---|---|---|---|
| 定位 | 快速概览 | 深入理解 | 彻底吃透 |
| 读取文件数 | ~45 | ~80 | ~150 |
| AI 输出 | 基础架构文档 | +数据流图、接口契约、设计决策 | +完整API参考、并发分析、反模式、测试覆盖 |
| 适合场景 | 初步评估项目 | 学习项目准备开发 | 代码审查、技术债梳理 |

### 文件名智能推断

自动从 80+ 关键词匹配文件角色，让 AI 在读代码之前就理解项目结构：

```
router.py  → 路由        models/  → 数据模型层
middleware → 中间件      services/ → 服务/业务逻辑
auth.py    → 认证        pipeline → 管线/流水线
config.py  → 配置        engine   → 引擎
```

### AI 对话：和"读过整个项目"的导师聊天

蒸馏完成后，进入对话模式：
- AI 已经持有完整的蒸馏笔记和关键源码作为知识基础
- **Agent Loop**：AI 可以自主请求读取项目中的任何源文件（最多 4 轮，每轮 5 个文件）
- **智能路径纠错**：AI 猜错了文件路径？系统自动把实际文件列表喂回去，让 AI 纠正后重试
- **三层上下文管理**：自动压缩旧对话 + 保留最近消息 + 按需读取文件，长对话不会"失忆"

### 对话管理

- 自建文件夹分组、拖拽排序、隐藏/取消隐藏
- 导出/导入对话（`.cdc` 格式，跨机器可迁移）
- 多 AI Provider 切换（Gemini / Claude / OpenAI / Ollama 本地模型）

## 支持的语言和框架

**语言**：Python, JavaScript, TypeScript, Java, Kotlin, Go, Rust, C/C++, C#, Ruby, PHP, Swift, Scala, Lua, SQL, Dart, Zig, Haskell, OCaml...

**依赖解析**：npm, pip, Cargo, Go Modules

**框架识别**：React, Vue, Next.js, Django, FastAPI, Flask, Spring, Gin, PyTorch, TensorFlow...

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python main.py
```

### 使用流程

1. **Settings** → 配置 AI Provider（填入 API Key）
2. **批量蒸馏 Tab** → 拖入项目文件夹 → 选择模式 → 点"开始蒸馏"
3. 等待 4 阶段分析完成（Phase 1 秒级，Phase 2-4 视项目大小约 1-3 分钟）
4. 自动跳转到**对话 Tab** → 开始和 AI 导师讨论项目

## 技术架构

```
┌─────────────────────────────────────────────────┐
│                   PySide6 GUI                    │
│  ┌──────────────┐    ┌───────────────────────┐   │
│  │  批量蒸馏 Tab  │    │      对话 Tab          │   │
│  │  · 拖拽文件夹  │    │  · Session 树 + 搜索   │   │
│  │  · 模式选择    │    │  · 消息气泡 + Agent    │   │
│  │  · 运行日志    │    │  · 快捷提问 + 配置     │   │
│  └──────┬───────┘    └───────────┬───────────┘   │
└─────────┼────────────────────────┼───────────────┘
          │                        │
┌─────────▼────────┐    ┌─────────▼────────────────┐
│   scanner.py     │    │       chat.py             │
│  Phase 1: 本地扫描 │    │  Agent Loop + 三层上下文   │
│  · 文件树 + 采矿   │    │  · [READ:] 文件读取       │
│  · Hub检测 + 角色  │    │  · 自动压缩 + 持久化      │
└─────────┬────────┘    └──────────────────────────┘
          │
┌─────────▼────────┐
│   analyzer.py    │
│  Phase 2-4: AI   │
│  · 结构 → 算法    │
│  · → 蒸馏笔记     │
│  · 渐进式缓存     │
└──────────────────┘
```

## 配置

所有配置持久化到 `~/.Code-Distiller/settings.json`：

- **AI Provider**：支持多个 Provider 并存，对话中可随时切换
- **蒸馏模式**：默认模式 + 每次蒸馏时可覆盖
- **蒸馏 Prompt**：完全可自定义分析 prompt
- **快捷提问**：自定义常用问题模板

## License

MIT License — 自由使用、修改和分发。
