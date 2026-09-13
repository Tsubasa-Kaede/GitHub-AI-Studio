# -*- coding: utf-8 -*-
"""
每日热榜流水线
==============

run_daily_trending_pipeline() 顺次执行：
    1. 抓取 GitHub Trending（页面解析，搜索 API 兜底）
    2. AI 按 USER_INTERESTS 筛选 Top N 并翻译为技术中文
    3. 补全 Star 数
    4. 多端推送（Ntfy / 飞书 / 钉钉 / 企微 / 邮件）
    5. Notion 自动归档（可选）

CLI 与 Streamlit 均调用本服务，保证行为一致。
"""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from typing import Callable, List, Optional, Sequence

import requests

from config import PROJECT_ROOT, settings
from core.ai_engine import AIEngine
from core.github_client import GitHubClientError
from core.notion_engine import NotionArchiver
from core.ntfy_engine import NtfyEngine
from models import PipelineResult, TrendingRepo

logger = logging.getLogger(__name__)
TRENDING_URL = "https://github.com/trending"
SEARCH_API = "https://api.github.com/search/repositories"

ProgressCb = Callable[[int, str], None]


def _get_with_proxy_fallback(url: str, **kwargs):
    """请求因代理不可达失败时，去掉代理直连重试一次（兼容 .env 配置了未启动的代理）。"""
    try:
        return requests.get(url, **kwargs)
    except requests.exceptions.ProxyError:
        logger.warning("代理不可达，尝试直连：%s", url)
        return requests.get(url, proxies={"http": None, "https": None}, **kwargs)

# ---------------------------------------------------------------------------
# 本地缓存（0-Click 预加载：启动/调度时静默写入，打开 UI 直接秒读）
# ---------------------------------------------------------------------------
CACHE_DIR = PROJECT_ROOT / "data"
CACHE_FILE = CACHE_DIR / "trending_cache.json"
CACHE_MAX_AGE_HOURS = 24


def _write_cache(payload: dict) -> None:
    """原子写入本地热榜缓存（先写临时文件再替换，避免半截 JSON）。"""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(CACHE_FILE)
    except OSError as exc:
        logger.warning("写入热榜缓存失败：%s", exc)


def _load_cache_raw() -> Optional[dict]:
    """读取缓存原始 dict；文件缺失/损坏返回 None。"""
    try:
        if not CACHE_FILE.exists():
            return None
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("items") else None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("读取热榜缓存失败：%s", exc)
        return None


def _merge_board(old_board: Optional[dict], items: Sequence[TrendingRepo]) -> dict:
    """合并旧看板状态：新榜单只保留仍存在的仓库，丢失项自动清理。"""
    old_board = old_board or {}
    board = {}
    for repo in items:
        prev = old_board.get(repo.name, {})
        board[repo.name] = {
            "status": prev.get("status", "new"),
            "notion_url": prev.get("notion_url"),
        }
    return board


def load_trending_cache() -> Optional[dict]:
    """读取热榜缓存（含 items 对象化 + 看板），供 UI 秒开。"""
    data = _load_cache_raw()
    if not data:
        return None
    data["items"] = [TrendingRepo.from_dict(item) for item in data.get("items", [])]
    data["board"] = data.get("board") or {}
    data["tags"] = data.get("tags") or []
    data["briefing"] = data.get("briefing") or ""
    return data


def save_cache_payload(
    items: Sequence[TrendingRepo],
    tags: Sequence[str],
    briefing: str,
    old_board: Optional[dict] = None,
) -> None:
    """把「抓取 + AI 分析」结果连同看板状态写入缓存。"""
    _write_cache({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tags": list(tags),
        "briefing": briefing,
        "board": _merge_board(old_board, items),
        "items": [repo.to_dict() for repo in items],
    })


def update_card_status(repo_name: str, status: str, notion_url: Optional[str] = None) -> bool:
    """更新看板中单张卡片状态（new / planned / archived），持久化到缓存。"""
    if status not in {"new", "planned", "archived"}:
        return False
    data = _load_cache_raw()
    if not data:
        return False
    board = data.setdefault("board", {})
    card = board.setdefault(repo_name, {})
    card["status"] = status
    if notion_url:
        card["notion_url"] = notion_url
    _write_cache(data)
    return True


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------
def fetch_github_trending(since: str = "daily", limit: int = 25, timeout: Optional[int] = None) -> List[TrendingRepo]:
    """抓取 GitHub Trending；页面失败时降级为搜索 API。"""
    timeout = timeout or settings.request_timeout
    since = since if since in {"daily", "weekly", "monthly"} else "daily"
    try:
        items = _fetch_trending_page(since, limit, timeout)
        if items:
            return items
    except Exception as exc:  # noqa: BLE001
        logger.warning("Trending 页面抓取失败：%s，降级为搜索 API。", exc)
    return _fetch_via_search_api(limit, timeout)


def _fetch_trending_page(since: str, limit: int, timeout: int) -> List[TrendingRepo]:
    from bs4 import BeautifulSoup

    resp = _get_with_proxy_fallback(
        TRENDING_URL, params={"since": since}, timeout=timeout,
        headers={"User-Agent": "Mozilla/5.0 (GitHub-AI-Studio)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items: List[TrendingRepo] = []
    for article in soup.select("article.Box-row")[:limit]:
        h2 = article.select_one("h2 a")
        if h2 is None:
            continue
        relative = h2.get("href", "").strip().lstrip("/").split("?")[0]
        if "/" not in relative:
            continue
        desc_tag = article.select_one("p")
        description = " ".join(desc_tag.get_text(" ", strip=True).split()) if desc_tag else ""
        lang_tag = article.select_one("[itemprop='programmingLanguage']")
        language = lang_tag.get_text(strip=True) if lang_tag else ""
        star_links = article.select("a[href$='/stargazers']")
        total = _parse_stars(star_links[0]) if len(star_links) > 0 else 0
        today = _parse_stars(star_links[-1]) if len(star_links) > 1 else total
        items.append(TrendingRepo(
            name=relative, url=f"https://github.com/{relative}",
            description=description, language=language,
            stars_total=total, stars_today=today,
        ))
    return items


def _parse_stars(tag) -> int:
    if tag is None:
        return 0
    text = tag.get("aria-label") or tag.get("title") or tag.get_text(" ", strip=True) or ""
    # 兼容 "1,234 stars"、"12.3k stars" 与 "1.2m stars" 三种格式
    match = re.search(r"([\d.,]+[km]?)\s*(star|⭐)", text, re.I)
    return _to_int(match.group(1)) if match else 0


def _to_int(raw: str) -> int:
    raw = raw.replace(",", "").strip().lower()
    try:
        if raw.endswith("k"):
            return int(float(raw[:-1]) * 1000)
        if raw.endswith("m"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(float(raw))
    except ValueError:
        return 0


def _fetch_via_search_api(limit: int, timeout: int) -> List[TrendingRepo]:
    """官方搜索 API 兜底：最近 7 天创建、Star 降序。"""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "GitHub-AI-Studio"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    resp = _get_with_proxy_fallback(
        SEARCH_API,
        params={
            "q": f"created:>={(date.today() - timedelta(days=7)).isoformat()}",
            "sort": "stars", "order": "desc", "per_page": min(limit, 100),
        },
        headers=headers, timeout=timeout,
    )
    resp.raise_for_status()
    return [
        TrendingRepo(
            name=r.get("full_name", ""), url=r.get("html_url", ""),
            description=r.get("description") or "", language=r.get("language") or "",
            stars_total=r.get("stargazers_count") or 0,
        )
        for r in resp.json().get("items", [])[:limit]
    ]


def enrich_stars(items: Sequence[TrendingRepo], timeout: Optional[int] = None) -> None:
    """补全总 Star 数（失败静默跳过）。"""
    if not items:
        return
    timeout = timeout or settings.request_timeout
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "GitHub-AI-Studio"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    for item in items:
        if item.stars_total:
            continue
        try:
            resp = _get_with_proxy_fallback(
                f"https://api.github.com/repos/{item.name}", headers=headers, timeout=timeout
            )
            resp.raise_for_status()
            item.stars_total = resp.json().get("stargazers_count") or 0
        except requests.RequestException as exc:
            logger.debug("补全 Star 失败 %s：%s", item.name, exc)


def _fetch_readme(name: str, timeout: int = 6) -> str:
    """抓取项目 README（raw.githubusercontent，多种大小写兜底）。"""
    headers = {"User-Agent": "GitHub-AI-Studio"}
    for candidate in ("README.md", "readme.md", "README", "Readme.md"):
        try:
            resp = requests.get(
                f"https://raw.githubusercontent.com/{name}/HEAD/{candidate}",
                headers=headers, timeout=timeout,
            )
            if resp.ok and resp.text.strip():
                return resp.text[:12000]
        except requests.RequestException:
            continue
    return ""


def _study_one(repo: TrendingRepo, ai: AIEngine) -> None:
    """为单个仓库生成深度研读报告并写回数据对象。"""
    readme = _fetch_readme(repo.name)
    data = ai.generate_repo_study(repo, readme)
    repo.overview = data.get("overview", "")
    repo.pain_points = data.get("pain_points", "")
    repo.features = list(data.get("features") or [])
    repo.use_cases = data.get("use_cases", "")
    repo.tech_highlights = data.get("tech_highlights", "")
    compact = ai.generate_compact_summary(repo, readme)
    repo.compact_position = compact.get("position", "")
    repo.compact_highlights = list(compact.get("highlights") or [])


def enrich_repo_study(items: Sequence[TrendingRepo], max_workers: int = 3) -> None:
    """并发提炼 Top N 项目的深度研读报告（README 抓取 + AI 结构化输出）。"""
    items = list(items)
    if not items:
        return
    ai = AIEngine()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as pool:
        futures = [pool.submit(_study_one, repo, ai) for repo in items]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:  # noqa: BLE001 —— 单条失败不影响其余
                logger.debug("深度研读失败：%s", exc)


# ---------------------------------------------------------------------------
# 两阶段流水线：阶段一「抓取 + AI 翻译」 / 阶段二「推送 + 归档」
# ---------------------------------------------------------------------------
def fetch_and_analyze_only(
    interests: Optional[Sequence[str]] = None,
    top_n: Optional[int] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> PipelineResult:
    """阶段一：只抓取热榜 + AI 筛选翻译（+ Star 补全），不做任何推送/归档。

    UI 点击「抓取并 AI 翻译」时调用，目标是把结果尽快渲染成卡片；
    手机推送与 Notion 归档交给 push_and_archive() 单独触发。
    """

    def emit(percent: int, message: str) -> None:
        if progress_cb:
            progress_cb(percent, message)

    interests = list(interests or settings.user_interests)
    top_n = top_n or settings.trending_top_n
    try:
        emit(10, "抓取 GitHub Trending...")
        items = fetch_github_trending(settings.trending_since, settings.trending_fetch_limit)
        if not items:
            return PipelineResult(success=False, error="未获取到热榜数据")

        emit(40, "AI 筛选与中文翻译...")
        selected = AIEngine().select_and_translate_trending(items, interests, top_n)
        if not selected:
            return PipelineResult(success=False, error="AI 筛选结果为空")

        emit(70, "补全 Star 数据...")
        enrich_stars(selected)
        emit(78, "生成深度项目研读报告（README 提炼）...")
        enrich_repo_study(selected)
        emit(88, "AI 生成技能雷达与简报...")
        briefing = AIEngine().generate_trending_briefing(selected, interests)
        old_cache = _load_cache_raw()
        save_cache_payload(
            selected,
            tags=briefing.get("tags", []),
            briefing=briefing.get("briefing", ""),
            old_board=old_cache.get("board") if old_cache else None,
        )
        emit(100, "完成（已写入本地缓存）")
        return PipelineResult(success=True, items=selected)
    except GitHubClientError as exc:
        return PipelineResult(success=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 —— 流水线兜底
        logger.exception("热榜抓取/翻译阶段异常")
        return PipelineResult(success=False, error=str(exc))


def push_and_archive(
    items: Sequence[TrendingRepo],
    do_push: bool = True,
    do_archive: bool = True,
    progress_cb: Optional[ProgressCb] = None,
) -> PipelineResult:
    """阶段二：对已抓取的热榜执行推送（Ntfy + 飞书）+ Notion 归档（可只推 / 只归档）。

    Ntfy / 飞书 / Notion 并行执行（最多 3 个通道线程），
    单条失败只记录日志，不阻断其他条目。
    """

    def emit(percent: int, message: str) -> None:
        if progress_cb:
            progress_cb(percent, message)

    items = list(items)
    if not items:
        return PipelineResult(success=False, error="没有可推送的热榜数据（请先执行抓取并 AI 翻译）")
    if not do_push and not do_archive:
        return PipelineResult(success=True, items=items)

    def _push_all() -> dict:
        ntfy = NtfyEngine()
        return ntfy.send_trending(items)

    def _archive_all() -> dict:
        archiver = NotionArchiver()
        return archiver.archive_many(items)

    def _feishu_all() -> dict:
        from core.feishu_engine import FeishuEngine

        feishu = FeishuEngine()
        cached = load_trending_cache()
        radar = cached["tags"] if cached else []
        ok, message = feishu.send_trending_digest(items, radar)
        return {"feishu": ok, "feishu_error": "" if ok else message}

    pushed: dict = {}
    notion_url: Optional[str] = None
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}
            if do_push:
                emit(15, "检查推送渠道...")
                if NtfyEngine().configured:
                    futures["push"] = pool.submit(_push_all)
                else:
                    logger.warning("未配置 NTFY_TOPIC，跳过手机推送。")
                from core.feishu_engine import FeishuEngine

                if FeishuEngine().configured:
                    futures["feishu"] = pool.submit(_feishu_all)
                else:
                    logger.warning("未配置 FEISHU_WEBHOOK_URL，跳过飞书推送。")
            if do_archive:
                emit(25, "检查 Notion 配置...")
                if NotionArchiver().configured:
                    futures["archive"] = pool.submit(_archive_all)
                else:
                    logger.warning("未配置 NOTION_TOKEN / NOTION_DATABASE_ID，跳过归档。")

            if not futures:
                emit(100, "完成（无可用渠道）")
                return PipelineResult(success=True, items=items)

            done_count = 0
            for name, future in futures.items():
                result = future.result()
                if name == "push":
                    pushed = result
                elif name == "feishu":
                    pushed["feishu"] = result.get("feishu", False)
                    if result.get("feishu_error"):
                        pushed["feishu_error"] = result["feishu_error"]
                else:
                    urls = result
                    notion_url = next(iter(urls.values()), None)
                done_count += 1
                emit(45 + done_count * 25, "推送/归档中...")

        emit(100, "完成")
        return PipelineResult(
            success=True, items=items, pushed_channels=pushed, notion_page_url=notion_url
        )
    except Exception as exc:  # noqa: BLE001 —— 推送/归档兜底
        logger.exception("热榜推送/归档阶段异常")
        return PipelineResult(success=False, error=str(exc))


def run_daily_trending_pipeline(
    interests: Optional[Sequence[str]] = None,
    top_n: Optional[int] = None,
    do_push: bool = True,
    do_archive: bool = True,
    progress_cb: Optional[ProgressCb] = None,
) -> PipelineResult:
    """执行完整热榜流水线（CLI / 托盘共用）：阶段一 + 阶段二。"""
    first = fetch_and_analyze_only(interests=interests, top_n=top_n, progress_cb=progress_cb)
    if not first.success:
        return first
    if not do_push and not do_archive:
        return first
    return push_and_archive(first.items, do_push=do_push, do_archive=do_archive, progress_cb=progress_cb)
