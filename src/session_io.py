"""
Code-Distiller 对话导出/导入模块
- 导出为 .cdc (ZIP) 归档，包含 session 数据 + 关联笔记
- 导入时自动重定向路径，生成新 session ID 避免冲突
"""

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

from .chat import _SESSIONS_DIR, load_folders, save_folders

_EXPORT_VERSION = 1


def export_sessions(session_ids: list[str], dest_path: str) -> bool:
    """将选中 sessions 打包为 .cdc ZIP 文件"""
    meta_sessions = []

    with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for sid in session_ids:
            session_dir = _SESSIONS_DIR / sid
            hfile = session_dir / "chat_history.json"
            if not hfile.is_file():
                continue

            data = json.loads(hfile.read_text(encoding="utf-8"))
            embedded = _embed_data_files(data, zf, sid)

            _rewrite_paths_export(data, embedded)

            folder_name = _get_folder_name(data.get("folder_id", ""))
            meta_sessions.append({
                "session_id": sid,
                "folder_name": folder_name,
                "name": data.get("name", sid),
            })

            zf.writestr(
                f"sessions/{sid}/chat_history.json",
                json.dumps(data, ensure_ascii=False, indent=2),
            )

        meta = {
            "version": _EXPORT_VERSION,
            "exported_at": datetime.now().isoformat(),
            "sessions": meta_sessions,
        }
        zf.writestr("export_meta.json", json.dumps(meta, ensure_ascii=False, indent=2))

    return len(meta_sessions) > 0


def import_sessions(cdc_path: str) -> list[str]:
    """从 .cdc 文件导入 sessions，返回新 session_id 列表"""
    new_ids = []

    with zipfile.ZipFile(cdc_path, "r") as zf:
        meta = json.loads(zf.read("export_meta.json"))
        meta_sessions = meta.get("sessions", [])

        for entry in meta_sessions:
            old_sid = entry["session_id"]
            prefix = f"sessions/{old_sid}/"

            names = [n for n in zf.namelist() if n.startswith(prefix)]
            if not names:
                continue

            # 创建新 session 目录（避免 ID 冲突）
            new_sid = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_dir = _SESSIONS_DIR / new_sid
            while new_dir.exists():
                new_sid += "_1"
                new_dir = _SESSIONS_DIR / new_sid

            new_dir.mkdir(parents=True, exist_ok=True)

            # 解压所有文件
            for name in names:
                rel = name[len(prefix):]
                if not rel:
                    continue
                target = new_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(target, "wb") as dst:
                    dst.write(src.read())

            # 重写文件路径为新绝对路径
            hfile = new_dir / "chat_history.json"
            if not hfile.is_file():
                continue

            data = json.loads(hfile.read_text(encoding="utf-8"))
            _rewrite_paths_import(data, str(new_dir))

            # 恢复文件夹分组
            folder_name = entry.get("folder_name", "")
            if folder_name:
                _ensure_folder(data, folder_name)

            hfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            new_ids.append(new_sid)

    return new_ids


# ─── 导出辅助 ───

def _embed_data_files(data: dict, zf: zipfile.ZipFile, sid: str) -> dict:
    """将关联文件复制到 ZIP，返回 {字段: 相对路径}"""
    embedded = {}

    notes_path = data.get("notes_path", "")
    if notes_path and os.path.isfile(notes_path):
        zf.write(notes_path, f"sessions/{sid}/notes.md")
        embedded["notes_path"] = "notes.md"

    return embedded


def _rewrite_paths_export(data: dict, embedded: dict):
    """导出时将绝对路径改为相对"""
    for key, rel in embedded.items():
        data[key] = rel
    # 清空项目路径（导入后需要用户重新配置）
    data["project_path"] = ""


def _get_folder_name(folder_id: str) -> str:
    if not folder_id:
        return ""
    folders = load_folders()
    for f in folders:
        if f["id"] == folder_id:
            return f["name"]
    return ""


# ─── 导入辅助 ───

def _rewrite_paths_import(data: dict, new_session_dir: str):
    """导入时将相对路径改为新绝对路径"""
    for key in ("notes_path",):
        rel = data.get(key, "")
        if not rel:
            continue
        if not os.path.isabs(rel):
            data[key] = os.path.join(new_session_dir, rel)


def _ensure_folder(data: dict, folder_name: str):
    """确保目标机器上存在同名文件夹"""
    if not folder_name:
        return
    folders = load_folders()
    for f in folders:
        if f["name"] == folder_name:
            data["folder_id"] = f["id"]
            return
    fid = datetime.now().strftime("%Y%m%d_%H%M%S")
    folders.append({"id": fid, "name": folder_name})
    save_folders(folders)
    data["folder_id"] = fid
