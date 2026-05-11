"""
Code-Distiller 代码分析模块
- Phase 2: 结构分析（AI 分析入口文件 + 模块关系）
- Phase 3: 算法深挖（AI 分析核心源码）
- Phase 4: 笔记生成（AI 生成结构化报告）

设计原则：渐进式分析，最大化 prompt 缓存命中
- Phase 2 的 system prompt 前缀 = Phase 1 扫描结果
- Phase 3 的 system prompt 前缀 = Phase 1 + Phase 2 结果
- Phase 4 的 system prompt 前缀 = Phase 1 + Phase 2 + Phase 3 结果
"""

import json
import os
from pathlib import Path
from typing import Optional, Callable

from .config import load_settings, LANG_MAP


# ─── AI 调用 ───

def _call_ai(system_prompt: str, user_message: str, provider: dict,
             max_tokens: int = 8192) -> tuple[str, int, int]:
    """调用 AI Provider，返回 (回复文本, 输入tokens, 输出tokens)"""
    import requests

    base_url = provider.get("base_url", "").rstrip("/")
    api_key = provider.get("api_key", "")
    model = provider.get("model", "")

    if not base_url or not api_key:
        raise ValueError("请先在设置中配置 AI Provider 的 URL 和 API Key")

    url = base_url + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": max_tokens,
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()

    reply = data["choices"][0]["message"]["content"].strip()
    usage = data.get("usage", {})
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    return reply, input_tokens, output_tokens


# ─── 文件读取 ───

def _read_file_content(project_path: str, rel_path: str, max_size_kb: int = 512) -> str:
    """读取文件内容，超过大小限制则截断"""
    full_path = Path(project_path) / rel_path
    if not full_path.exists():
        return ""
    try:
        size_kb = full_path.stat().st_size / 1024
        if size_kb > max_size_kb:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
            if len(lines) > 200:
                return "\n".join(lines[:100] + ["\n... (省略中间部分) ...\n"] + lines[-50:])
            return content[:30000] + "\n... (文件过大，已截断)"
        return full_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _collect_source_files(project_path: str, file_list: list[str],
                          max_files: int = 30, max_size_kb: int = 512) -> str:
    """收集源码文件内容，拼装为文本"""
    settings = load_settings()
    code_exts = set(LANG_MAP.keys())
    parts = []

    count = 0
    for rel in file_list:
        ext = Path(rel).suffix.lower()
        if ext not in code_exts:
            continue
        content = _read_file_content(project_path, rel, max_size_kb)
        if content:
            parts.append(f"### 文件: {rel}\n```\n{content}\n```")
            count += 1
            if count >= max_files:
                break

    return "\n\n".join(parts)


# ─── Phase 2: 结构分析 ───

STRUCTURE_PROMPT = """你是一位资深代码架构师。以下是一个代码项目的扫描结果。
请分析项目的架构和模块结构，严格按以下格式输出：

## 入口与启动流程
描述项目从入口文件到核心逻辑的调用链路。

## 模块划分
列出主要模块/目录及其职责。

## 设计模式
识别项目中使用的设计模式（如 MVC、MVVM、插件架构、工厂模式等）。

## 数据流向
描述核心数据在模块之间的流动路径。

## 关键接口
列出核心接口、API 端点、事件总线等关键连接点。

## 建议的深挖文件
列出 5-10 个最值得深入分析的核心文件（按重要性排序），用相对路径表示。

只输出分析结果，不要重复扫描信息。"""

_HIGH_STRUCTURE_EXTRA = """
额外要求（深入模式）：
- 对每个识别的模块，说明其职责并用具体文件名作为证据
- 描述模块间的数据流向（从入口到存储的完整路径）
- 列出模块间的接口契约（函数签名、事件、回调）
- 识别错误处理模式和异常传播链
- 标注配置的层级关系（默认值 < 配置文件 < 环境变量）
- 建议的深挖文件扩展到 10-20 个
"""

_ULTRA_STRUCTURE_EXTRA = """
额外要求（极致模式）：
- 完整的模块依赖图（每个模块依赖哪些其他模块）
- 每个公开 API 的签名和用途
- 每个设计模式的证据（具体在哪个文件）
- 并发模型分析（线程、异步、锁、队列）
- 代码中的反模式和潜在问题
- 测试覆盖评估（哪些模块有测试，哪些没有）
- 安全性分析（输入验证、权限检查、敏感数据处理）
- 性能关键路径标注
- 建议的深挖文件扩展到 20-30 个
"""


def _get_structure_prompt(mode: str) -> str:
    if mode == "ultra":
        return STRUCTURE_PROMPT + _ULTRA_STRUCTURE_EXTRA
    if mode == "high":
        return STRUCTURE_PROMPT + _HIGH_STRUCTURE_EXTRA
    return STRUCTURE_PROMPT


def analyze_structure(scan_summary: str, entry_contents: str,
                      provider: dict, progress_cb=None,
                      mode: str = "normal") -> tuple[str, dict]:
    """Phase 2: 分析项目结构

    Args:
        scan_summary: Phase 1 扫描结果文本（将被缓存）
        entry_contents: 入口文件内容（增量发送）
        provider: AI Provider 配置
        progress_cb: 进度回调
        mode: normal / high / ultra

    Returns:
        (分析结果文本, token 统计)
    """
    if progress_cb:
        progress_cb("正在分析项目结构...")

    prompt = _get_structure_prompt(mode)
    max_tokens = {"normal": 8192, "high": 8192, "ultra": 16384}.get(mode, 8192)

    system_prompt = f"以下是项目扫描结果：\n\n{scan_summary}"
    user_message = f"{prompt}\n\n--- 入口文件内容 ---\n{entry_contents}"

    reply, in_tokens, out_tokens = _call_ai(system_prompt, user_message, provider, max_tokens=max_tokens)

    return reply, {"input_tokens": in_tokens, "output_tokens": out_tokens}


# ─── Phase 3: 算法深挖 ───

ALGORITHM_PROMPT = """你是一位资深算法工程师。在前面项目扫描和结构分析的基础上，
现在我会给你提供核心源码文件。请深入分析这些代码中的关键算法和数据结构。

## 核心算法
按模块列出关键算法，每个算法包含：
- 算法名称和用途
- 时间复杂度和空间复杂度
- 核心思路（2-3 句话）

## 数据结构
列出项目中自定义的数据结构及其用途。

## 性能热点
标注可能的性能瓶颈或优化空间。

## 设计亮点
指出代码中值得学习的设计技巧和实现细节。

只输出分析结果。"""

_HIGH_ALGORITHM_EXTRA = """
额外要求（深入模式）：
- 每个算法给出具体的代码位置（文件:函数名）
- 分析算法的输入输出边界条件
- 分析内存使用模式（是否有大对象、缓存策略）
- 每个数据结构标注是否线程安全
"""

_ULTRA_ALGORITHM_EXTRA = """
额外要求（极致模式）：
- 每个算法给出完整的行为描述和边界条件分析
- 性能基准估算（基于代码复杂度推算）
- 算法的可测试性评估
- 数据流图：数据从创建到最终使用的完整生命周期
- 与同类实现的对比（如果使用了标准库或第三方实现）
- 分析所有错误处理路径和异常边界
"""


def _get_algorithm_prompt(mode: str) -> str:
    if mode == "ultra":
        return ALGORITHM_PROMPT + _ULTRA_ALGORITHM_EXTRA
    if mode == "high":
        return ALGORITHM_PROMPT + _HIGH_ALGORITHM_EXTRA
    return ALGORITHM_PROMPT


def analyze_algorithms(scan_summary: str, structure_analysis: str,
                       core_contents: str, provider: dict,
                       progress_cb=None,
                       mode: str = "normal") -> tuple[str, dict]:
    """Phase 3: 深挖核心算法

    Args:
        scan_summary: Phase 1 扫描结果（缓存前缀）
        structure_analysis: Phase 2 结构分析结果（缓存前缀）
        core_contents: 核心源码内容（增量发送）
        provider: AI Provider 配置
        progress_cb: 进度回调
        mode: normal / high / ultra

    Returns:
        (分析结果文本, token 统计)
    """
    if progress_cb:
        progress_cb("正在分析核心算法...")

    prompt = _get_algorithm_prompt(mode)
    max_tokens = {"normal": 8192, "high": 8192, "ultra": 16384}.get(mode, 8192)

    system_prompt = (
        f"以下是项目扫描结果：\n\n{scan_summary}\n\n"
        f"--- 结构分析 ---\n{structure_analysis}"
    )
    user_message = f"{prompt}\n\n--- 核心源码 ---\n{core_contents}"

    reply, in_tokens, out_tokens = _call_ai(system_prompt, user_message, provider, max_tokens=max_tokens)

    return reply, {"input_tokens": in_tokens, "output_tokens": out_tokens}


# ─── Phase 4: 笔记生成 ───

def generate_notes(scan_summary: str, structure_analysis: str,
                   algorithm_analysis: str, provider: dict,
                   custom_prompt: str = "", progress_cb=None,
                   mode: str = "normal") -> tuple[str, dict]:
    """Phase 4: 生成蒸馏笔记

    Args:
        scan_summary: Phase 1 扫描结果（缓存前缀）
        structure_analysis: Phase 2 结构分析（缓存前缀）
        algorithm_analysis: Phase 3 算法分析（缓存前缀）
        provider: AI Provider 配置
        custom_prompt: 自定义分析 Prompt（覆盖默认）
        progress_cb: 进度回调
        mode: normal / high / ultra

    Returns:
        (笔记文本, token 统计)
    """
    if progress_cb:
        progress_cb("正在生成蒸馏笔记...")

    settings = load_settings()
    prompt = custom_prompt or settings.default_analysis_prompt
    max_tokens = {"normal": 8192, "high": 8192, "ultra": 16384}.get(mode, 8192)

    if mode == "high":
        prompt += _HIGH_NOTES_EXTRA
    elif mode == "ultra":
        prompt += _ULTRA_NOTES_EXTRA

    system_prompt = (
        f"以下是项目扫描结果：\n\n{scan_summary}\n\n"
        f"--- 结构分析 ---\n{structure_analysis}\n\n"
        f"--- 算法分析 ---\n{algorithm_analysis}"
    )
    user_message = prompt

    reply, in_tokens, out_tokens = _call_ai(system_prompt, user_message, provider, max_tokens=max_tokens)

    return reply, {"input_tokens": in_tokens, "output_tokens": out_tokens}


_HIGH_NOTES_EXTRA = """

## 模块详解
对每个核心模块，给出：
- 职责边界（负责什么，不负责什么）
- 核心类/函数清单（签名 + 一句话说明）
- 与其他模块的交互方式

## 数据流图
用文字描述主要数据在系统中的流动路径。

## 设计决策
识别关键的设计决策及其权衡（为什么这样设计，而不是其他方案）。
"""

_ULTRA_NOTES_EXTRA = """

## 完整 API 参考
列出所有核心模块的公开 API（函数签名、参数说明、返回值）。

## 并发与安全
线程模型、锁机制、异步模式、数据竞争风险评估。

## 反模式与改进建议
识别代码中的反模式、技术债、潜在 bug，给出改进建议。

## 测试覆盖地图
哪些模块有测试，覆盖了什么场景，哪些场景缺失。
"""


# ─── 智能文件选择 ───

def select_files_for_analysis(project_path: str, scan_result, phase: int,
                              mode: str = "normal") -> list[str]:
    """根据分析阶段和模式选择要发送给 AI 的文件

    Phase 2:
      normal: 入口文件 + 配置文件 (max 15)
      high:   入口文件 + hub文件 + 配置文件 (max 30)
      ultra:  入口文件 + hub文件 + 配置文件 + 角色关键文件 (max 50)
    """
    if phase == 2:
        files = list(scan_result.entry_files)
        files.extend(scan_result.config_files[:5])

        if mode in ("high", "ultra"):
            # 添加 hub 文件（被引用最多的文件）
            hub_paths = [h["path"] for h in (scan_result.hub_files or [])]
            files.extend(hub_paths[:10])

        if mode == "ultra":
            # 添加角色关键文件（核心/引擎/入口/配置/路由 等角色的文件）
            key_roles = {"核心", "引擎", "入口", "路由", "管线", "配置",
                         "API", "中间件", "服务层", "数据模型"}
            if scan_result.file_roles:
                for path, role in scan_result.file_roles.items():
                    if role in key_roles:
                        files.append(path)

        # 去重
        seen = set()
        unique = []
        for f in files:
            if f not in seen:
                seen.add(f)
                unique.append(f)

        max_files = {"normal": 15, "high": 30, "ultra": 50}.get(mode, 15)
        return unique[:max_files]

    return []


def select_core_files_from_analysis(structure_text: str, project_path: str) -> list[str]:
    """从结构分析结果中提取建议深挖的文件路径"""
    import re
    files = []
    # 匹配相对路径模式，如 src/foo/bar.py, app/main.ts 等
    for line in structure_text.splitlines():
        line = line.strip().lstrip("- •*0-9. ")
        # 检查是否像文件路径
        if "/" in line and ("." in line.split()[0]):
            candidate = line.split()[0].strip("`'\"")
            if (Path(project_path) / candidate).exists():
                files.append(candidate)
    return files[:30]
