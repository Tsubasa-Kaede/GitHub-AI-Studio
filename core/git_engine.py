# -*- coding: utf-8 -*-
"""
Git 原子引擎（GitPython 封装）
==============================

只提供最基础的 Git 能力（init / diff / commit / push / tag / log），
业务编排（一键托管、发版）由 services 层负责。
所有异常统一翻译为 GitEngineError（中文提示）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from git import GitCommandError, InvalidGitRepositoryError, NoSuchPathError, Repo


class GitEngineError(RuntimeError):
    """本地 Git 操作失败。"""


# Diff 送入 AI 的最大长度（防止 Token 超限）
MAX_DIFF_CHARS = 60_000
MAX_UNTRAKED_PREVIEW_LINES = 60

DEFAULT_GITIGNORE = """# Python
__pycache__/
*.py[cod]
.venv/
venv/
env/

# 环境与密钥
.env
.env.*
!.env.example
*.pem
*.key

# 依赖与构建
node_modules/
dist/
build/
*.egg-info/

# IDE / 系统
.idea/
.vscode/
*.swp
.DS_Store

# 日志
logs/
*.log
"""


@dataclass
class DiffResult:
    """一次 diff 提取结果。"""

    has_changes: bool
    diff_text: str
    diff_stat: str
    staged_files: List[str] = field(default_factory=list)
    unstaged_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        """变更文件总数。"""
        return len(self.staged_files) + len(self.unstaged_files) + len(self.untracked_files)


def _friendly(action: str, exc: Exception) -> GitEngineError:
    """把 Git 异常转成中文友好错误。"""
    message = str(exc).strip().lower()
    if "authentication failed" in message or "could not read username" in message:
        hint = "认证失败：请检查 Git 凭据（GITHUB_TOKEN / gh CLI）是否有效。"
    elif "non-fast-forward" in message or "fetch first" in message or "rejected" in message:
        hint = "推送被拒绝：远程分支存在本地没有的提交，请先 git pull --rebase。"
    else:
        hint = str(exc).strip()
    return GitEngineError(f"{action} 失败：{hint}")


# ---------------------------------------------------------------------------
# 仓库初始化 / 打开
# ---------------------------------------------------------------------------
def is_git_repo(path: Path) -> bool:
    """判断目录是否已是 Git 仓库。"""
    try:
        Repo(str(path))
        return True
    except Exception:
        return False


def init_repo(path: Path, default_branch: str = "main") -> Repo:
    """初始化 Git 仓库（已是仓库则复用），并把默认分支改为指定名称。"""
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    try:
        if is_git_repo(path):
            return Repo(str(path))
        repo = Repo.init(str(path))
        repo.git.symbolic_ref("HEAD", f"refs/heads/{default_branch}")
        return repo
    except (GitCommandError, InvalidGitRepositoryError, OSError) as exc:
        raise GitEngineError(f"初始化 Git 仓库失败（{path}）：{exc}") from exc


def get_repo(path: Path) -> Repo:
    """打开已有 Git 仓库。"""
    path = Path(path).resolve()
    try:
        return Repo(str(path))
    except InvalidGitRepositoryError as exc:
        raise GitEngineError(f"目录不是 Git 仓库：{path}") from exc
    except NoSuchPathError as exc:
        raise GitEngineError(f"目录不存在：{path}") from exc


def has_commits(repo: Repo) -> bool:
    """是否已有首个提交。"""
    try:
        repo.git.rev_parse("--verify", "HEAD")
        return True
    except GitCommandError:
        return False


def get_current_branch(repo: Repo) -> str:
    """当前分支名（分离 HEAD 时返回短哈希）。"""
    try:
        return repo.active_branch.name
    except (TypeError, ValueError):
        try:
            return repo.git.rev_parse("--abbrev-ref", "HEAD")
        except GitCommandError:
            return "HEAD"


# ---------------------------------------------------------------------------
# 状态 / Diff
# ---------------------------------------------------------------------------
def get_status_summary(repo: Repo) -> Dict[str, List[str]]:
    """返回 {staged, unstaged, untracked} 三组文件列表。"""
    return {
        "staged": [p for p in repo.git.diff("--cached", "--name-only").splitlines() if p],
        "unstaged": [p for p in repo.git.diff("--name-only").splitlines() if p],
        "untracked": list(repo.untracked_files),
    }


def get_diff(repo: Repo, include_untracked: bool = True) -> DiffResult:
    """提取工作区 + 暂存区变更（兼容全新仓库与未跟踪文件）。"""
    staged = [p for p in repo.git.diff("--cached", "--name-only").splitlines() if p]
    unstaged = [p for p in repo.git.diff("--name-only").splitlines() if p]
    untracked = list(repo.untracked_files)

    if has_commits(repo):
        try:
            diff_text = repo.git.diff("HEAD")
            diff_stat = repo.git.diff("HEAD", "--stat")
        except GitCommandError as exc:
            raise GitEngineError(f"提取 diff 失败：{exc}") from exc
    else:
        diff_text = repo.git.diff("--cached") + repo.git.diff()
        diff_stat = (repo.git.diff("--cached", "--stat") + repo.git.diff("--stat")).strip()

    preview = _untracked_preview(repo, untracked) if include_untracked and untracked else ""
    combined = (diff_text.strip() + "\n" + preview).strip()
    if len(combined) > MAX_DIFF_CHARS:
        combined = combined[:MAX_DIFF_CHARS] + "\n...(diff 过长，已截断)"

    return DiffResult(
        has_changes=bool(combined) or bool(staged) or bool(unstaged) or bool(untracked),
        diff_text=combined,
        diff_stat=diff_stat.strip(),
        staged_files=staged,
        unstaged_files=unstaged,
        untracked_files=untracked,
    )


def _untracked_preview(repo: Repo, untracked_files: Sequence[str]) -> str:
    """未跟踪文件内容预览（跳过敏感文件 / 大文件 / 二进制）。"""
    root = Path(repo.working_dir)
    lines = ["", "## 未跟踪文件预览（提交时将全部加入）"]
    for name in untracked_files:
        path = root / name
        lines.append(f"\n### {name}")
        if not path.is_file():
            lines.append("(目录或非常规文件)")
            continue
        if name == ".env" or name.endswith(".env"):
            lines.append("(敏感环境变量文件，跳过预览)")
            continue
        if path.stat().st_size > 200_000:
            lines.append("(文件过大，跳过预览)")
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            lines.append("(无法读取)")
            continue
        lines.extend(content.splitlines()[:MAX_UNTRAKED_PREVIEW_LINES])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 提交 / 推送 / 远程
# ---------------------------------------------------------------------------
def stage_all(repo: Repo) -> None:
    """暂存全部变更。"""
    try:
        repo.git.add("-A")
    except GitCommandError as exc:
        raise GitEngineError(f"暂存文件失败：{exc}") from exc


def commit(repo: Repo, message: str, stage_first: bool = False) -> str:
    """创建提交，返回短哈希。"""
    if stage_first:
        stage_all(repo)
    if not message.strip():
        raise GitEngineError("提交信息不能为空。")
    try:
        return repo.index.commit(message.strip()).hexsha[:8]
    except GitCommandError as exc:
        raise GitEngineError(f"创建提交失败：{exc}") from exc


def push(repo: Repo, remote_name: str = "origin", branch: Optional[str] = None, force: bool = False) -> str:
    """推送到远程仓库，识别认证失败 / 非快进冲突。"""
    branch = branch or get_current_branch(repo)
    try:
        remote = repo.remote(remote_name)
    except ValueError as exc:
        raise GitEngineError(f"远程仓库 {remote_name!r} 不存在，请先 add_remote()。") from exc
    try:
        infos = remote.push(refspec=f"{branch}:{branch}", force=force)
    except GitCommandError as exc:
        raise _friendly(f"推送到 {remote_name}/{branch}", exc) from exc
    problems = []
    for info in infos:
        if info.flags & info.ERROR:
            problems.append(f"推送错误: {info.summary}")
        elif info.flags & info.REJECTED:
            problems.append(f"推送被拒绝: {info.summary}")
    if problems:
        raise GitEngineError("推送失败：" + "；".join(problems) + "。建议先 git pull --rebase。")
    return f"{remote_name}/{branch} ✓"


def add_remote(repo: Repo, name: str, url: str) -> None:
    """添加远程仓库；同名已存在则更新 URL。"""
    try:
        if name in [r.name for r in repo.remotes]:
            repo.remote(name).set_url(url)
        else:
            repo.create_remote(name, url)
    except (GitCommandError, ValueError) as exc:
        raise GitEngineError(f"配置远程仓库失败：{exc}") from exc


def has_remote(repo: Repo, name: str = "origin") -> bool:
    """是否已存在指定远程。"""
    return name in [r.name for r in repo.remotes]


# ---------------------------------------------------------------------------
# Tag / 提交历史
# ---------------------------------------------------------------------------
def list_tags(repo: Repo) -> List[str]:
    """列出本地标签（按版本倒序优先）。"""
    try:
        return [t.name for t in repo.tags]
    except GitCommandError as exc:
        raise GitEngineError(f"读取标签失败：{exc}") from exc


def get_commits_since(repo: Repo, since_tag: Optional[str], to_ref: str = "HEAD", limit: int = 100) -> str:
    """返回 since_tag 之后的提交摘要；无 Tag 时返回最近 limit 条。"""
    try:
        if since_tag:
            return repo.git.log(
                f"{since_tag}..{to_ref}",
                "--pretty=format:%h %ad %an %s",
                "--date=short",
                "-n", str(limit),
            )
        return repo.git.log(
            "--pretty=format:%h %ad %an %s", "--date=short", "-n", str(limit)
        )
    except GitCommandError as exc:
        raise GitEngineError(f"读取提交历史失败：{exc}") from exc


def get_commits_since_date(repo: Repo, since_date: str, to_ref: str = "HEAD", limit: int = 200) -> str:
    """返回指定日期（ISO 格式，如 2026-08-02）以来的提交摘要（工作日报用）。"""
    try:
        return repo.git.log(
            "--since", since_date,
            "--pretty=format:%h %ad %an %s",
            "--date=short",
            "-n", str(limit),
        )
    except GitCommandError as exc:
        raise GitEngineError(f"读取提交历史失败：{exc}") from exc


# ---------------------------------------------------------------------------
# 项目辅助
# ---------------------------------------------------------------------------
def get_tree_summary(repo: Repo, max_entries: int = 80) -> str:
    """顶层目录结构摘要（供 AI 生成 README）。"""
    root = Path(repo.working_dir)
    skip = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
    entries = []
    for item in sorted(root.iterdir()):
        name = item.name
        if name in skip or (name.startswith(".") and name not in {".github", ".gitignore"}):
            continue
        entries.append(name + ("/" if item.is_dir() else ""))
    return "\n".join(entries[:max_entries])


def ensure_gitignore(repo: Repo) -> bool:
    """仓库缺少 .gitignore 时写入默认模板，返回是否新建。"""
    gitignore = Path(repo.working_dir) / ".gitignore"
    try:
        if gitignore.exists() and gitignore.stat().st_size > 0:
            return False
        gitignore.write_text(DEFAULT_GITIGNORE, encoding="utf-8")
        return True
    except OSError as exc:
        raise GitEngineError(f"写入 .gitignore 失败：{exc}") from exc
