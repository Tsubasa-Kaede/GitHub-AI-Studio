# -*- coding: utf-8 -*-
"""
代码安全扫描引擎
=================

两类能力：
    1. 硬编码密钥扫描：GitHub Token（含 fine-grained）、OpenAI Key、私钥、JWT、通用密钥赋值；
    2. 依赖漏洞扫描：解析 requirements.txt / package.json，调用 OSV.dev 免费 API
       查询已知漏洞（无需 API Key）。

供「AI Commit」与「一键托管」流水线在提交前调用。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger(__name__)

# 敏感信息正则（含 GitHub Fine-grained Token）
SENSITIVE_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("GitHub Fine-grained Token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("GitHub Token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("OpenAI API Key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS Access Key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT Token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "硬编码密钥赋值",
        re.compile(
            r"(?i)\b(api[_-]?key|secret|password|passwd|token|access[_-]?key|client[_-]?secret)\b"
            r"\s*[:=]\s*['\"][^'\"]{8,}['\"]"
        ),
    ),
]

OSV_API = "https://api.osv.dev/v1/query"


class SecurityGuard:
    """代码安全扫描器。"""

    # ------------------------------------------------------------------
    # 硬编码密钥扫描
    # ------------------------------------------------------------------
    def scan_text(self, text: str) -> List[dict]:
        """扫描文本，返回 [{pattern, line, snippet}]。"""
        findings = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern_name, pattern in SENSITIVE_PATTERNS:
                if pattern.search(line) and not self._is_example(line):
                    findings.append({
                        "pattern": pattern_name,
                        "line": line_no,
                        "snippet": line.strip()[:120],
                    })
                    break
        return findings

    def scan_path(self, root: Path, max_bytes: int = 1_000_000) -> List[dict]:
        """递归扫描目录文本文件，返回 [{file, line, pattern, snippet}]。"""
        if isinstance(root, str):
            root = Path(root)
        skip_dirs = {
            ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
            ".idea", ".vscode", "logs", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        }
        binary_ext = {
            ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
            ".exe", ".dll", ".so", ".dylib", ".woff", ".woff2", ".ttf", ".pyc", ".lock",
        }
        findings: List[dict] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
            for fname in filenames:
                path = Path(dirpath) / fname
                if fname == ".env" or fname.endswith(".env") or path.suffix.lower() in binary_ext:
                    continue
                try:
                    if path.stat().st_size > max_bytes:
                        continue
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for hit in self.scan_text(text):
                    hit["file"] = str(path.relative_to(root))
                    findings.append(hit)
        return findings

    @staticmethod
    def _is_example(line: str) -> bool:
        """过滤示例 / 占位符 / 模板变量，减少误报。"""
        if "${" in line or "{{" in line:
            return True
        lowered = line.lower()
        match = re.search(r"[:=]\s*['\"]([^'\"]*)", lowered)
        if not match:
            return False  # 无引号值的裸密钥不视为示例
        value = match.group(1).strip()
        if not value:
            return True  # 空引号占位
        placeholder_markers = (
            "example", "sample", "placeholder", "your-key", "your_key",
            "your-token", "your_token", "xxx", "changeme", "demo",
        )
        return any(marker in value for marker in placeholder_markers)

    # ------------------------------------------------------------------
    # 依赖漏洞扫描（OSV.dev）
    # ------------------------------------------------------------------
    def scan_dependencies(self, root: Path, timeout: int = 12) -> List[dict]:
        """解析依赖清单并查询 OSV 已知漏洞。

        返回 [{package, version, ecosystem, vulns: [{id, summary}]}]。
        """
        if isinstance(root, str):
            root = Path(root)
        packages: List[Dict[str, str]] = []
        req_file = root / "requirements.txt"
        if req_file.exists():
            packages += self._parse_requirements(req_file)
        pkg_json = root / "package.json"
        if pkg_json.exists():
            packages += self._parse_package_json(pkg_json)
        if not packages:
            return []

        findings: List[dict] = []
        for pkg in packages:
            try:
                resp = requests.post(
                    OSV_API,
                    json={
                        "package": {"name": pkg["name"], "ecosystem": pkg["ecosystem"]},
                        "version": pkg["version"],
                    },
                    timeout=timeout,
                )
                resp.raise_for_status()
                vulns = resp.json().get("vulns") or []
                if vulns:
                    findings.append({
                        "package": pkg["name"],
                        "version": pkg["version"],
                        "ecosystem": pkg["ecosystem"],
                        "vulns": [
                            {"id": v.get("id", ""), "summary": (v.get("summary") or "")[:160]}
                            for v in vulns[:5]
                        ],
                    })
            except requests.RequestException as exc:
                logger.debug("OSV 查询失败 %s==%s：%s", pkg["name"], pkg["version"], exc)
        return findings

    @staticmethod
    def _parse_requirements(path: Path) -> List[Dict[str, str]]:
        """解析 requirements.txt 中锁定版本的依赖（name==version）。"""
        packages = []
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return packages
        for line in lines:
            line = line.split("#")[0].strip()
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s*==\s*([A-Za-z0-9_.-]+)", line)
            if match:
                packages.append({
                    "name": match.group(1).lower(),
                    "version": match.group(2),
                    "ecosystem": "PyPI",
                })
        return packages

    @staticmethod
    def _parse_package_json(path: Path) -> List[Dict[str, str]]:
        """解析 package.json 的 dependencies / devDependencies（精确版本）。"""
        packages = []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            return packages
        for section in ("dependencies", "devDependencies"):
            for name, version in (data.get(section) or {}).items():
                if re.fullmatch(r"\d+\.\d+\.\d+.*", version):
                    packages.append({
                        "name": name,
                        "version": version.lstrip("^~"),
                        "ecosystem": "npm",
                    })
        return packages
