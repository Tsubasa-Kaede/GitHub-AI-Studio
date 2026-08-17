# -*- coding: utf-8 -*-
"""
OpenAI 原子引擎（结构化输出）
=============================

功能：
    1. 生成 Conventional Commits 提交信息；
    2. 生成专业 README；
    3. 热榜筛选 + 技术中文翻译（JSON 结构化输出）；
    4. CHANGELOG 分类格式化（JSON 结构化输出）；
    5. PR 代码审查（Markdown 报告）；
    6. 敏感信息扫描（提交前拦截）。

AI 不可用或调用失败时，根据 AI_FALLBACK_ENABLED 自动降级为本地规则，
保证流水线不因模型问题中断。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI
from openai import APIError, APITimeoutError, AuthenticationError, RateLimitError

from config import settings
from models import RepoInfo, TrendingRepo

MAX_PROMPT_CHARS = 40_000

# 防直译约束：技术专有名词必须保留英文原文（核心翻译规范）
ANTI_TRANSLITERATION = (
    "翻译约束：所有的编程语言名称（如 Jupyter Notebook, Python, Rust）、"
    "框架及开源工具名（如 Docker, PyTorch, Agent），"
    "【必须严格保留英文原文】，绝对禁止音译或直译！"
)

class AIEngineError(RuntimeError):
    """AI 引擎错误。"""


class AIEngine:
    """OpenAI 对话封装：统一异常翻译 + JSON 结构化输出。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = base_url if base_url is not None else settings.openai_base_url or None
        self._enabled_override = enabled
        self._client: Optional[OpenAI] = None

    @property
    def enabled(self) -> bool:
        """AI 是否可用（显式开关优先）。"""
        if self._enabled_override is not None:
            return self._enabled_override
        return bool(self.api_key)

    # ------------------------------------------------------------------
    def _get_client(self) -> OpenAI:
        if not self.enabled:
            raise AIEngineError("未配置 OPENAI_API_KEY，AI 功能不可用（可降级为本地规则）。")
        if self._client is None:
            kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": settings.request_timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def _chat(self, system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 2000) -> str:
        """普通文本对话，统一翻译 OpenAI 异常。"""
        try:
            response = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (response.choices[0].message.content or "").strip()
        except AuthenticationError as exc:
            raise AIEngineError("OPENAI_API_KEY 无效或已过期，请检查配置。") from exc
        except RateLimitError as exc:
            raise AIEngineError("OpenAI 速率限制或余额不足，请稍后重试。") from exc
        except APITimeoutError as exc:
            raise AIEngineError(f"OpenAI 请求超时（{settings.request_timeout}s）。") from exc
        except APIError as exc:
            raise AIEngineError(f"OpenAI API 错误：{exc}") from exc

    def _chat_json(self, system: str, user: str, *, temperature: float = 0.2, max_tokens: int = 2000) -> dict:
        """JSON 结构化对话（response_format=json_object）。"""
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        try:
            response = self._get_client().chat.completions.create(**payload)
            raw = (response.choices[0].message.content or "").strip()
            return json.loads(raw)
        except (AuthenticationError, RateLimitError, APITimeoutError, APIError) as exc:
            if isinstance(exc, AuthenticationError):
                raise AIEngineError("OPENAI_API_KEY 无效或已过期，请检查配置。") from exc
            if isinstance(exc, RateLimitError):
                raise AIEngineError("OpenAI 速率限制或余额不足，请稍后重试。") from exc
            if isinstance(exc, APITimeoutError):
                raise AIEngineError(f"OpenAI 请求超时（{settings.request_timeout}s）。") from exc
            raise AIEngineError(f"OpenAI API 错误：{exc}") from exc
        except json.JSONDecodeError as exc:
            raise AIEngineError("AI 返回内容无法解析为 JSON，请重试或降级。") from exc

    # ------------------------------------------------------------------
    def ping(self) -> dict:
        """连通性测试：发送极短 Prompt，返回 {"ok", "message", "elapsed_ms"}。"""
        import time

        if not self.enabled:
            return {"ok": False, "message": "未配置 OPENAI_API_KEY", "elapsed_ms": 0}
        start = time.perf_counter()
        try:
            reply = self._chat(
                "你是连通性测试助手。", "请只回复：OK",
                temperature=0.0, max_tokens=8,
            )
            return {
                "ok": True,
                "message": (reply or "OK")[:24],
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            }
        except AIEngineError as exc:
            return {
                "ok": False,
                "message": str(exc),
                "elapsed_ms": int((time.perf_counter() - start) * 1000),
            }

    # ------------------------------------------------------------------
    # 1) AI Commit Message
    # ------------------------------------------------------------------
    def generate_commit_message(self, diff_text: str, diff_stat: str = "", hint: str = "") -> str:
        """根据 diff 生成 Conventional Commits 提交信息。"""
        diff_text = (diff_text or "").strip()
        if not diff_text:
            raise AIEngineError("Diff 为空，无法生成提交信息。")
        if not self.enabled:
            return self._fallback_commit_message(diff_text)
        system = (
            "你是资深 Git 提交信息专家。严格遵循 Conventional Commits："
            "type(scope): subject，type 为 feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert。"
            "subject 用祈使句、≤72 字符；复杂变更可附简短 body。只输出提交信息本身。"
        )
        user = f"""根据以下 Diff 生成提交信息。
{hint and f"补充要求：{hint}" or ""}
【统计】{diff_stat[:2000] or "(无)"}
【Diff】{diff_text[:MAX_PROMPT_CHARS]}
"""
        try:
            return self._normalize_commit_message(self._chat(system, user, temperature=0.3, max_tokens=500))
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_commit_message(diff_text)
            raise

    def _normalize_commit_message(self, raw: str) -> str:
        """清洗模型输出。"""
        text = raw.strip()
        text = re.sub(r"^```(?:[a-zA-Z]+)?\s*|\s*```$", "", text).strip()
        text = re.sub(r"^['\"]|['\"]$", "", text).strip()
        lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return "chore: update"
        if not re.match(r"^[a-z]+(\([^)]*\))?!?:", lines[0]):
            lines[0] = f"chore: {lines[0][:60]}"
        return "\n".join(lines[:12]).strip()

    def _fallback_commit_message(self, diff_text: str) -> str:
        """本地规则：按文件类型猜测提交类型。"""
        lowered = diff_text[:8000].lower()
        files = re.findall(r"diff --git a/(.+?) b/", diff_text) or re.findall(r"^\+\+\+ b/(.+)$", diff_text, re.M)
        joined = " ".join(files).lower()
        if "test" in joined or "_test" in joined:
            type_ = "test"
        elif "docs/" in joined or joined.endswith(".md"):
            type_ = "docs"
        elif ".github/" in joined or "dockerfile" in joined:
            type_ = "ci"
        elif "requirements" in joined or "package" in joined or "pyproject" in joined:
            type_ = "build"
        elif "fix" in lowered or "bug" in lowered:
            type_ = "fix"
        elif "feat" in lowered or "add" in lowered or "new" in lowered:
            type_ = "feat"
        else:
            type_ = "chore"
        scope = ""
        if files:
            first = files[0].split("/")[-1].split(".")[0][:20]
            if first:
                scope = f"({first})"
        return f"{type_}{scope}: update {len(files)} file(s)" if files else f"{type_}: update"

    # ------------------------------------------------------------------
    # 2) AI README
    # ------------------------------------------------------------------
    def generate_readme(self, project_name: str, tree_summary: str = "", language_hints: str = "") -> str:
        """生成专业中文 README。"""
        if not self.enabled:
            return self._fallback_readme(project_name, language_hints)
        system = (
            "你是资深开源项目文档专家。生成结构清晰的中文 README.md，包含：项目简介、"
            "核心特性（emoji 列表）、快速开始、目录结构、配置说明、许可证。直接输出 Markdown。"
        )
        user = f"""项目：{project_name}
技术栈：{language_hints or "（未提供）"}
目录结构：
{tree_summary[:6000] or "（无）"}
"""
        try:
            return self._chat(system, user, temperature=0.5, max_tokens=2500)
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_readme(project_name, language_hints)
            raise

    def _fallback_readme(self, project_name: str, language_hints: str = "", lang: str = "zh-CN") -> str:
        """本地 README 模板（AI 不可用 / 指定语言时使用）。"""
        return f"""# {project_name}

{project_name} —— 由 GitHub-AI-Studio 自动初始化。

## ✨ 特性
- 🚀 一键托管：本地目录初始化 Git 仓库并推送 GitHub
- 🤖 AI 加持：智能 Commit / README / CHANGELOG 生成
- 🔥 中文热榜：AI 筛选与翻译 GitHub Trending，推送手机并归档 Notion

## 🚀 快速开始
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 📄 许可证
MIT
"""

    def generate_readme_i18n(
        self,
        project_name: str,
        tree_summary: str = "",
        language_hints: str = "",
        languages: Sequence[str] = ("zh-CN", "en"),
    ) -> Dict[str, str]:
        """生成多语言 README：返回 {文件名: Markdown 内容}。

        约定：zh-CN → README.md（主文档），其余语言 → README.<code>.md。
        """
        result: Dict[str, str] = {}
        for lang in languages:
            filename = "README.md" if lang == "zh-CN" else f"README.{lang}.md"
            if not self.enabled:
                result[filename] = self._fallback_readme(project_name, language_hints, lang)
                continue
            system = (
                f"你是资深开源项目文档专家。请生成 {lang} 语言版本的专业 README.md，"
                "包含：项目简介、核心特性（emoji 列表）、快速开始、目录结构、许可证。"
                + ANTI_TRANSLITERATION
            )
            user = f"""项目：{project_name}
技术栈：{language_hints or "（未提供）"}
目录结构：
{tree_summary[:6000] or "（无）"}
"""
            try:
                result[filename] = self._chat(system, user, temperature=0.5, max_tokens=2500)
            except AIEngineError:
                if settings.ai_fallback_enabled:
                    result[filename] = self._fallback_readme(project_name, language_hints, lang)
                else:
                    raise
        return result

    # ------------------------------------------------------------------
    # 3) 热榜筛选 + 技术中文翻译（结构化输出）
    # ------------------------------------------------------------------
    def select_and_translate_trending(
        self, repos: Sequence[TrendingRepo], interests: Sequence[str], top_n: int = 3
    ) -> List[TrendingRepo]:
        """按用户兴趣筛选 Top N，并生成中文技术定位与摘要。

        模型返回 JSON：
        {"matches": [{"index": 0, "zh_position": "...", "zh_summary": "...", "reason": "..."}]}
        中文文案保留专业英文名词（如 Agent、LLM、RAG）。
        """
        repos = list(repos)
        if not repos:
            return []
        top_n = max(1, min(top_n, len(repos)))
        if not self.enabled:
            return self._heuristic_translate(repos, interests, top_n)

        payload = [
            {
                "index": i,
                "name": r.name,
                "description": r.description[:300],
                "language": r.language,
                "stars": r.stars_total,
            }
            for i, r in enumerate(repos)
        ]
        system = (
            "你是 GitHub 热榜选品与翻译专家。根据用户兴趣标签选出最相关 Top N 个项目。"
            "【硬性约束】所有项目名与 GitHub 账号名必须严格保留英文原格式 owner/repo，"
            "严禁翻译、音译或改写项目名与账号名；中文定位/摘要中如需提及项目，一律使用原始英文名。"
            "必须返回 JSON：{\"matches\": [{\"index\": 数字, "
            "\"score\": 0-10 的匹配度评分（小数一位）, "
            "\"tags\": [2-4 个技术标签（保留英文原文）], "
            "\"zh_position\": \"20-40字中文技术定位（保留专业英文名词）\", "
            "\"zh_summary\": \"30-60字中文亮点摘要（专业、地道）\", "
            "\"learning_points\": \"1-2 条核心学习点（中文，每条 ≤24 字，用 / 分隔）\", "
            "\"reason\": \"匹配原因\"}]}。"
            "index 必须是候选列表真实下标；只返回 JSON。"
            + ANTI_TRANSLITERATION
        )
        user = f"""用户兴趣：{', '.join(interests)}
Top N：{top_n}
候选：
{json.dumps(payload, ensure_ascii=False)[:MAX_PROMPT_CHARS]}
"""
        try:
            data = self._chat_json(system, user, temperature=0.2, max_tokens=1500)
            matches = data.get("matches") or []
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._heuristic_translate(repos, interests, top_n)
            raise

        selected: List[TrendingRepo] = []
        seen: set = set()
        for m in matches:
            idx = m.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(repos) or idx in seen:
                continue
            seen.add(idx)
            repo = repos[idx]
            try:
                repo.match_score = round(float(m.get("score", 0) or 0), 1)
            except (TypeError, ValueError):
                repo.match_score = 0.0
            repo.tags = [str(t).strip() for t in (m.get("tags") or []) if str(t).strip()][:4]
            repo.zh_position = (m.get("zh_position") or "").strip()
            repo.zh_summary = (m.get("zh_summary") or "").strip()
            repo.learning_points = (m.get("learning_points") or "").strip()
            repo.match_reason = (m.get("reason") or "").strip()
            selected.append(repo)
            if len(selected) >= top_n:
                break

        if len(selected) < top_n:
            used = {r.name for r in selected}
            for r in self._heuristic_translate(repos, interests, top_n):
                if r.name not in used:
                    selected.append(r)
                if len(selected) >= top_n:
                    break
        return selected

    def _heuristic_translate(
        self, repos: Sequence[TrendingRepo], interests: Sequence[str], top_n: int
    ) -> List[TrendingRepo]:
        """本地规则：关键词匹配 + Star 加权；无 AI 时不翻译，保留原文并标注。"""
        keywords = [k.lower() for k in interests if k]
        scored: List[Tuple[float, int]] = []
        for i, r in enumerate(repos):
            haystack = f"{r.name} {r.description} {r.language}".lower()
            score = sum(2 if kw in haystack else 0 for kw in keywords if len(kw) >= 2)
            score += min(r.stars_total / 5000, 3)
            scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], -repos[x[1]].stars_total))
        result = []
        for _, idx in scored[:top_n]:
            repo = repos[idx]
            matched_keywords = [
                kw for kw in keywords
                if len(kw) >= 2 and kw in f"{repo.name} {repo.description} {repo.language}".lower()
            ]
            repo.match_score = round(
                min(10.0, 5.0 + len(matched_keywords) * 1.5 + min(repo.stars_total / 100_000, 3.0)), 1
            )
            repo.tags = [repo.language] if repo.language else []
            repo.tags += [kw.title() for kw in matched_keywords[:3]]
            repo.zh_position = f"{repo.language or '多语言'} · 开源项目"
            repo.zh_summary = f"{repo.description[:80] or '热门开源项目'}（AI 未启用，暂为原文摘要）"
            repo.learning_points = repo.zh_summary
            repo.match_reason = "关键词/热度匹配（本地规则）"
            result.append(repo)
        return result

    # ------------------------------------------------------------------
    # 3.5) 今日技能雷达 + 30 秒文本简报（结构化输出）
    # ------------------------------------------------------------------
    def generate_trending_briefing(
        self, repos: Sequence[TrendingRepo], interests: Sequence[str]
    ) -> dict:
        """汇总热榜生成「技能雷达标签 + 30s 中文简报」。

        返回 {"tags": [..], "briefing": ".."}；AI 不可用时用本地规则降级。
        """
        repos = list(repos)
        if not repos:
            return {"tags": [], "briefing": ""}
        if not self.enabled:
            return self._fallback_briefing(repos, interests)

        payload = [
            {
                "name": r.name,
                "language": r.language,
                "tags": list(r.tags),
                "summary": r.zh_summary or r.description[:120],
            }
            for r in repos
        ]
        system = (
            "你是 GitHub 技术趋势分析师。根据今日热榜与用户兴趣生成："
            "1) 技能雷达标签：2-4 个最值得关注的技术方向（英文原文，如 Python / AI Agent / RAG）；"
            "2) 30 秒文本简报：约 120-160 字中文，可 30 秒读完，提炼今日趋势亮点。"
            '必须返回 JSON：{"tags": [".."], "briefing": ".."}。'
            + ANTI_TRANSLITERATION
        )
        user = f"""用户兴趣：{', '.join(interests)}
今日热榜：
{json.dumps(payload, ensure_ascii=False)[:MAX_PROMPT_CHARS]}
"""
        try:
            data = self._chat_json(system, user, temperature=0.3, max_tokens=700)
            tags = [str(t).strip() for t in (data.get("tags") or []) if str(t).strip()][:4]
            briefing = (data.get("briefing") or "").strip()
            return {"tags": tags, "briefing": briefing}
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_briefing(repos, interests)
            raise

    @staticmethod
    def _fallback_briefing(repos: Sequence[TrendingRepo], interests: Sequence[str]) -> dict:
        """本地规则简报：语言标签 + 摘要拼接（AI 不可用时）。"""
        tags: List[str] = []
        for r in repos:
            if r.language and r.language not in tags:
                tags.append(r.language)
        for r in repos:
            for t in r.tags:
                if t not in tags:
                    tags.append(t)
        tags = tags[:4]
        lines = [
            f"- {r.name}（{r.language or '多语言'}）：{(r.zh_summary or r.description)[:60]}"
            for r in repos[:3]
        ]
        briefing = (
            f"今日热榜围绕你的兴趣（{', '.join(interests) or '默认'}）筛选出 {len(repos)} 个项目。"
            + " ".join(lines)
            + "（AI 未启用，暂为本地摘要）"
        )
        return {"tags": tags, "briefing": briefing}

    # ------------------------------------------------------------------
    # 3.6) 深度项目研读报告（基于 README 的结构化提炼）
    # ------------------------------------------------------------------
    def generate_repo_study(self, repo: TrendingRepo, readme_text: str = "") -> dict:
        """根据项目 README 提炼五维研读报告。

        返回：
            {"overview": str, "pain_points": str, "features": [str],
             "use_cases": str, "tech_highlights": str}
        项目名与账号名一律保留英文原文；AI 不可用或无 README 时本地降级。
        """
        from core.llm_summary import apply_section_rules

        fallback = self._fallback_repo_study(repo)
        if not self.enabled or not (readme_text or "").strip():
            return apply_section_rules(fallback)
        system = (
            "你是资深开源项目分析师。根据 GitHub 项目的 README 提炼一份深度研读报告，"
            "【硬性约束】项目名与 GitHub 账号名必须严格保留英文原格式 owner/repo，"
            "严禁翻译、音译或改写项目名与账号名；"
            "【字数约束】每个字段（含每条 features）字数严格控制在 25~30 字，超长直接截断。"
            '必须返回 JSON：{"overview": "2~3 句话的深度项目背景与创立初衷（中文）", '
            '"pain_points": "1~2 条该项目解决的痛点（中文，带具体语境）", '
            '"features": ["3~4 条核心功能特性，每条含细节说明（中文）"], '
            '"use_cases": "适用场景与目标人群（中文）", '
            '"tech_highlights": "架构与技术优势（中文，保留 Python/TypeScript/Rust 等英文专有名词）"}。'
            + ANTI_TRANSLITERATION
        )
        user = f"""项目：{repo.name}
语言：{repo.language or '未知'} · Stars：{repo.stars_total}
原始描述：{repo.description[:500] or '（无）'}

【README 内容】
{(readme_text or '')[:12000]}
"""
        try:
            data = self._chat_json(system, user, temperature=0.25, max_tokens=1600)
            return apply_section_rules({
                "overview": str(data.get("overview") or fallback["overview"]).strip(),
                "pain_points": str(data.get("pain_points") or fallback["pain_points"]).strip(),
                "features": [
                    str(f).strip() for f in (data.get("features") or [])
                    if str(f).strip()
                ][:4] or fallback["features"],
                "use_cases": str(data.get("use_cases") or fallback["use_cases"]).strip(),
                "tech_highlights": str(
                    data.get("tech_highlights") or fallback["tech_highlights"]
                ).strip(),
            })
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return apply_section_rules(fallback)
            raise

    @staticmethod
    def _fallback_repo_study(repo: TrendingRepo) -> dict:
        """本地降级研读报告（无 AI / 无 README 时）。"""
        features = [f for f in (repo.learning_points or repo.zh_summary or "").split("/") if f.strip()]
        return {
            "overview": repo.zh_summary or repo.description or f"{repo.name} 开源项目",
            "pain_points": repo.match_reason or "（暂未提炼，配置 OPENAI_API_KEY 后可生成深度分析）",
            "features": features[:3] or ["多技术栈实践 / 工程化参考"],
            "use_cases": f"适合关注 {', '.join(repo.tags[:3]) or '开源技术'} 的开发者",
            "tech_highlights": (
                f"{repo.language or '多语言'} · {', '.join(repo.tags[:3]) or '待 AI 分析'}"
            ),
        }

    # ------------------------------------------------------------------
    # 3.7) 极致精炼总结（一眼扫完，max_tokens=300）
    # ------------------------------------------------------------------
    def generate_compact_summary(self, repo: TrendingRepo, readme_text: str = "") -> dict:
        """生成极简总结：{"position", "highlights"}。

        硬性约束（见 core/llm_summary.COMPACT_SUMMARY_SYSTEM_PROMPT）：
            定位 ≤35 字、亮点每条 ≤25 字、整篇 ≤120 字；输出后强制二次压缩。
        """
        from core.llm_summary import (
            COMPACT_SUMMARY_SYSTEM_PROMPT,
            apply_compact_rules,
            split_features,
        )

        fallback = {
            "position": (
                repo.compact_position or repo.zh_position
                or repo.overview or repo.description or "开源项目"
            ),
            "highlights": repo.compact_highlights or repo.features or split_features(repo),
        }
        if not self.enabled or not (readme_text or "").strip():
            return apply_compact_rules(fallback)

        user = f"""项目：{repo.name}
语言：{repo.language or '未知'} · Stars：{repo.stars_total}
原始描述：{repo.description[:300] or '（无）'}

【README 内容】
{(readme_text or '')[:10000]}
"""
        try:
            data = self._chat_json(
                COMPACT_SUMMARY_SYSTEM_PROMPT, user,
                temperature=0.2, max_tokens=300,
            )
            return apply_compact_rules({
                "position": data.get("position"),
                "highlights": data.get("highlights"),
            })
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return apply_compact_rules(fallback)
            raise

    # ------------------------------------------------------------------
    # 4) CHANGELOG 格式化（结构化输出）
    # ------------------------------------------------------------------
    def format_changelog(self, commits_text: str, tag: str) -> Dict[str, List[str]]:
        """把提交历史分类为 JSON：features / fixes / improvements / breaking / other。"""
        if not commits_text.strip():
            raise AIEngineError("提交历史为空，无法生成 CHANGELOG。")
        if not self.enabled:
            return self._fallback_changelog(commits_text)
        system = (
            "你是开源项目维护者。把 Git 提交历史分类为中文 CHANGELOG 数据，必须返回 JSON："
            '{"features": ["..."], "fixes": ["..."], "improvements": ["..."], '
            '"breaking": ["..."], "other": ["..."]}。'
            "每个条目保留提交短哈希并附中文说明；无对应类别则返回空数组。"
        )
        user = f"""版本：{tag}
【提交历史】
{commits_text[:MAX_PROMPT_CHARS]}
"""
        try:
            data = self._chat_json(system, user, temperature=0.2, max_tokens=1800)
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_changelog(commits_text)
            raise
        return {
            key: [str(x) for x in (data.get(key) or []) if str(x).strip()]
            for key in ("features", "fixes", "improvements", "breaking", "other")
        }

    @staticmethod
    def compose_changelog_markdown(data: Dict[str, List[str]], tag: str) -> str:
        """把分类 JSON 组装为规范 Markdown CHANGELOG。"""
        sections = [
            ("🚀 新功能", "features"),
            ("🐛 Bug 修复", "fixes"),
            ("🧰 优化项", "improvements"),
            ("⚠️ 破坏性变更", "breaking"),
            ("📦 其他", "other"),
        ]
        lines = [f"## {tag}", ""]
        for title, key in sections:
            items = data.get(key) or []
            if items:
                lines.append(f"### {title}")
                lines.extend(f"- {item}" for item in items)
                lines.append("")
        return "\n".join(lines).strip() or f"## {tag}\n\n本次发布无显著变更。"

    def _fallback_changelog(self, commits_text: str) -> Dict[str, List[str]]:
        """本地规则分类（关键词 + Conventional Commits 前缀）。"""
        groups: Dict[str, List[str]] = {
            "features": [], "fixes": [], "improvements": [], "breaking": [], "other": []
        }
        for line in commits_text.splitlines():
            lowered = line.lower()
            if "!" in line and re.search(r"\b(feat|fix|refactor)\b\s*!?", line):
                groups["breaking"].append(line)
            elif re.search(r"\bfeat\b", lowered) or "新功能" in line:
                groups["features"].append(line)
            elif re.search(r"\bfix\b", lowered) or "修复" in line or "bug" in lowered:
                groups["fixes"].append(line)
            elif re.search(r"\b(refactor|perf|optimize|improve|style|docs)\b", lowered):
                groups["improvements"].append(line)
            else:
                groups["other"].append(line)
        return groups

    # ------------------------------------------------------------------
    # 5) PR 代码审查（Markdown 报告）
    # ------------------------------------------------------------------
    def review_code(self, diff_text: str, repo_context: str = "") -> str:
        """审查 diff 并输出 Markdown 报告（供 GitHub Actions 使用）。"""
        diff_text = (diff_text or "").strip()
        if not diff_text:
            return "# 🤖 AI 代码审查报告\n\n本次 PR 没有代码变更，无需审查。"
        if not self.enabled:
            return self._fallback_review(diff_text)
        system = (
            "你是资深代码审查专家。用中文 Markdown 输出审查报告，包含：总体评价、潜在 Bug、"
            "安全问题、性能问题、可读性、改进建议（按优先级）、综合评分。每个问题给出文件/行号/原因/建议。"
        )
        user = f"""{repo_context and f"上下文：{repo_context[:1500]}" or ""}
【Diff】
{diff_text[:MAX_PROMPT_CHARS]}
"""
        try:
            report = self._chat(system, user, temperature=0.2, max_tokens=3500)
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_review(diff_text)
            raise
        header = "# 🤖 AI 代码审查报告"
        return f"{header}\n\n{report}" if not report.startswith("#") else report

    def _fallback_review(self, diff_text: str) -> str:
        """本地规则基础审查。"""
        added = [ln for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        issues = []
        if any(re.search(r"print\s*\(", ln) for ln in added):
            issues.append("- 存在 `print` 调试输出，建议使用日志模块。")
        if any(re.search(r"(?i)todo|fixme|hack", ln) for ln in added):
            issues.append("- 存在 TODO/FIXME 标记，建议清理。")
        if any("password" in ln.lower() or "secret" in ln.lower() for ln in added):
            issues.append("- 新增代码出现敏感字段关键字，请确认未硬编码密钥。")
        if not issues:
            issues.append("- 本地规则未发现明显问题（配置 OPENAI_API_KEY 可获得深度审查）。")
        return (
            "# 🤖 AI 代码审查报告\n\n## 🔍 总体评价\n"
            f"本次变更新增 {len(added)} 行（本地规则模式）。\n\n"
            "## ✅ 改进建议\n" + "\n".join(issues) + "\n\n## 🎯 综合评分\n70/100"
        )

    # ------------------------------------------------------------------
    # 6) Star 仓库语义搜索
    # ------------------------------------------------------------------
    def semantic_search_starred(
        self, repos: Sequence[RepoInfo], query: str, top_n: int = 5
    ) -> List[dict]:
        """自然语言语义搜索 Star 仓库，返回 [{repo, score, reason}]。"""
        repos = list(repos)
        if not repos or not query.strip():
            return []
        top_n = max(1, min(top_n, len(repos)))
        if not self.enabled:
            return self._heuristic_star_search(repos, query, top_n)

        payload = [
            {
                "index": i,
                "name": r.full_name,
                "description": r.description[:300],
                "language": r.language,
            }
            for i, r in enumerate(repos)
        ]
        system = (
            "你是 GitHub 仓库推荐专家。根据用户的自然语言需求，从候选 Star 仓库中挑选最匹配的 Top N。"
            '必须返回 JSON：{"matches": [{"index": 数字, "score": 0-10, "reason": "匹配原因（中文）"}]}。'
            "index 必须是候选列表真实下标；只返回 JSON。"
            + ANTI_TRANSLITERATION
        )
        user = f"""用户需求：{query}
Top N：{top_n}
候选仓库：
{json.dumps(payload, ensure_ascii=False)[:MAX_PROMPT_CHARS]}
"""
        try:
            data = self._chat_json(system, user, temperature=0.2, max_tokens=1500)
            matches = data.get("matches") or []
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._heuristic_star_search(repos, query, top_n)
            raise

        result: List[dict] = []
        seen: set = set()
        for m in matches:
            idx = m.get("index")
            if not isinstance(idx, int) or idx < 0 or idx >= len(repos) or idx in seen:
                continue
            seen.add(idx)
            try:
                score = round(float(m.get("score", 0) or 0), 1)
            except (TypeError, ValueError):
                score = 0.0
            result.append({
                "repo": repos[idx],
                "score": score,
                "reason": (m.get("reason") or "").strip(),
            })
            if len(result) >= top_n:
                break
        if len(result) < top_n:
            used = {r["repo"].full_name for r in result}
            for r in self._heuristic_star_search(repos, query, top_n):
                if r["repo"].full_name not in used:
                    result.append(r)
                if len(result) >= top_n:
                    break
        return result

    def _heuristic_star_search(
        self, repos: Sequence[RepoInfo], query: str, top_n: int
    ) -> List[dict]:
        """本地关键词搜索降级（AI 不可用时）。"""
        keywords = [k for k in re.split(r"[\s,，、]+", query.lower()) if len(k) >= 2]
        scored: List[tuple] = []
        for i, r in enumerate(repos):
            hay = f"{r.full_name} {r.description} {r.language}".lower()
            score = sum(2 if kw in hay else 0 for kw in keywords)
            score += min(r.stars / 100_000, 1.5)
            scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], -repos[x[1]].stars))
        result = []
        for _, idx in scored[:top_n]:
            repo = repos[idx]
            matched = sum(1 for kw in keywords if kw in f"{repo.full_name} {repo.description}".lower())
            result.append({
                "repo": repo,
                "score": round(min(10.0, 3.0 + matched * 2.0), 1),
                "reason": f"关键词命中 {matched} 项（本地规则）",
            })
        return result

    # ------------------------------------------------------------------
    # 7) Git 工作日报 / 周报
    # ------------------------------------------------------------------
    def generate_worklog(self, commits_text: str, period: str = "today") -> str:
        """把 Git 提交记录汇总为结构化 Markdown 工作日报。"""
        if not commits_text.strip():
            return f"# {period} 工作记录\n\n该周期内暂无提交。"
        if not self.enabled:
            return self._fallback_worklog(commits_text, period)
        system = (
            "你是开发者效率助手。把 Git 提交记录整理为结构化中文 Markdown 工作日报："
            "# 工作日报 / ## 📌 完成事项 / ## 🛠️ 技术要点 / ## 📊 统计。"
            "按时间归纳并保留提交短哈希。"
            + ANTI_TRANSLITERATION
        )
        user = f"""统计周期：{period}
【提交记录】
{commits_text[:MAX_PROMPT_CHARS]}
"""
        try:
            return self._chat(system, user, temperature=0.3, max_tokens=2000)
        except AIEngineError:
            if settings.ai_fallback_enabled:
                return self._fallback_worklog(commits_text, period)
            raise

    def _fallback_worklog(self, commits_text: str, period: str) -> str:
        """本地规则工作日报（无 AI 时）。"""
        lines = [f"# {period} 工作记录", "", "## 📊 统计",
                 f"- 共 {len([ln for ln in commits_text.splitlines() if ln.strip()])} 条提交", "",
                 "## 📌 提交记录"]
        lines += [f"- {ln}" for ln in commits_text.splitlines()[:60]]
        return "\n".join(lines)
