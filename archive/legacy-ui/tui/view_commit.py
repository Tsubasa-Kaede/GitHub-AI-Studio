# -*- coding: utf-8 -*-
"""视图 2：📝 AI Commit & 代码安全扫描控制台。"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Static, TextArea

from core.ai_engine import AIEngine
from core.git_engine import commit, get_diff, get_repo, has_remote, push, stage_all
from core.security_guard import SecurityGuard


class CommitView(Vertical):
    """AI 智能提交视图：读取 diff → 安全扫描 → AI 提交信息 → 提交推送。"""

    def compose(self) -> ComposeResult:
        yield Label("📝 AI 智能 Commit & 代码安全扫描")
        yield Input(placeholder="本地 Git 仓库路径", id="commit_path")
        yield Horizontal(
            Button("🔍 读取 Diff", id="commit_diff"),
            Button("🛡️ 安全扫描", id="commit_scan"),
            Button("🤖 AI 生成提交信息", id="commit_ai"),
            Button("⬆️ 提交并推送", id="commit_push", variant="primary"),
        )
        yield TextArea("", id="commit_message")
        yield Static("", id="commit_output")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """分发按钮动作到对应后台任务。"""
        mapping = {
            "commit_diff": self._load_diff,
            "commit_scan": self._scan,
            "commit_ai": self._ai_message,
            "commit_push": self._commit_push,
        }
        handler = mapping.get(event.button.id)
        if handler:
            self.run_worker(handler(), thread=True)

    def _output(self) -> Static:
        return self.query_one("#commit_output", Static)

    async def _load_diff(self) -> None:
        try:
            path = self.query_one("#commit_path", Input).value.strip()
            diff = get_diff(get_repo(path))
            self._output().update(
                f"变更文件：{diff.file_count}\n{diff.diff_stat or '(无统计)'}\n\n"
                f"{diff.diff_text[:3000]}"
            )
            self.notify(f"共 {diff.file_count} 个文件变更")
        except Exception as exc:  # noqa: BLE001
            self._output().update(f"❌ {exc}")

    async def _scan(self) -> None:
        try:
            path = self.query_one("#commit_path", Input).value.strip()
            hits = SecurityGuard().scan_path(path)
            if hits:
                lines = "\n".join(
                    f"⛔ {h['file']}:{h['line']} [{h['pattern']}] {h['snippet']}" for h in hits[:10]
                )
                self._output().update(f"发现 {len(hits)} 处敏感信息：\n{lines}")
                self.notify(f"发现 {len(hits)} 处敏感信息！", severity="error")
            else:
                self._output().update("✅ 未发现硬编码密钥。")
        except Exception as exc:  # noqa: BLE001
            self._output().update(f"❌ {exc}")

    async def _ai_message(self) -> None:
        try:
            path = self.query_one("#commit_path", Input).value.strip()
            diff = get_diff(get_repo(path))
            if not diff.has_changes:
                self._output().update("✅ 工作区干净，没有需要提交的变更。")
                return
            message = AIEngine().generate_commit_message(diff.diff_text, diff.diff_stat)
            self.query_one("#commit_message", TextArea).text = message
            self._output().update("✅ AI 提交信息已生成，可在上方编辑后提交。")
        except Exception as exc:  # noqa: BLE001
            self._output().update(f"❌ {exc}")

    async def _commit_push(self) -> None:
        try:
            path = self.query_one("#commit_path", Input).value.strip()
            message = self.query_one("#commit_message", TextArea).text.strip()
            if not message:
                self._output().update("❌ 提交信息不能为空。")
                return
            repo = get_repo(path)
            # 提交前安全拦截
            hits = SecurityGuard().scan_text(get_diff(repo).diff_text)
            if hits:
                self._output().update(f"⛔ 敏感信息拦截：{hits[0]['pattern']}（第 {hits[0]['line']} 行）")
                self.notify("已拦截敏感信息，未提交", severity="error")
                return
            if not has_remote(repo):
                self._output().update("❌ 未配置 origin 远程，请先在「一键托管」建仓。")
                return
            stage_all(repo)
            short = commit(repo, message)
            push(repo, "origin")
            self._output().update(f"✅ 已提交 {short} 并推送：{message.splitlines()[0]}")
            self.notify("提交并推送成功", severity="success")
        except Exception as exc:  # noqa: BLE001
            self._output().update(f"❌ {exc}")
