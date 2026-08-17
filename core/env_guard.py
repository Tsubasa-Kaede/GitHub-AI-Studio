# -*- coding: utf-8 -*-
"""
环境变量文件提交防护
===================

在 `git add -A` 之前识别工作区中即将被提交的环境变量文件
（.env / .env.*，.env.example 除外），避免真实密钥入库。
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def is_env_file(name: str) -> bool:
    """判断文件名是否属于环境变量文件（.env.example 为模板，不算）。"""
    base = Path(name).name
    return base == ".env" or (base.startswith(".env.") and base != ".env.example")


def unignored_env_files(repo) -> List[str]:
    """列出未被 .gitignore 忽略、且会被 `git add -A` 加入暂存区的环境变量文件。"""
    try:
        untracked = repo.git.ls_files("--others", "--exclude-standard").splitlines()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"检测未忽略环境变量文件失败：{exc}") from exc
    return [path for path in untracked if path and is_env_file(path)]
