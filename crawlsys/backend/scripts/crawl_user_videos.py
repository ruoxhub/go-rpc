"""单独跑 getUserVideo 任务：遍历用户列表，分页抓取其内容列表并下载媒体到 MinIO。

与常驻 Worker 不同，本脚本是一次性任务：
  1. 用户来源二选一：
     - `--user-list <file>`：从文本文件读取用户标识（每行一个，普通用户 ID/uniqueId），
       对每个用户先调 getUserInfo 获取用户信息入库，并从响应中解析出 secuid；
     - 默认：查询 t_busi_user 中已有的用户（按 platform 过滤），从 extend 解析 secuid；
  2. 对每个用户调用 getUserVideo，按 cursor 翻页直到 hasMore=false 或游标不再推进；
  3. 解析结果（content + user）经标准 Pipeline（Bloom 去重 + upsert）入库；
  4. `--download` 开启时，对解析出的每条 content 用 download_media 下载
     视频/音频/封面并上传 MinIO（bucket=平台，对象 `{content_id}/video|audio|pic`），
     成功后回写内容的 extend（minio 对象名）与 is_download 标志。

依赖外部 go-rpc 服务（config.toml 中的 rpc_base_url）在线，与 Worker 共用同一端点；
`--download` 还需要 config.toml 的 [minio] 与 [proxy] 配置。

用法:
    python scripts/crawl_user_videos.py --user-list user_list.txt
    python scripts/crawl_user_videos.py --user-list user_list.txt --download
    python scripts/crawl_user_videos.py --platform tiktok --limit 50 --offset 0
    python scripts/crawl_user_videos.py --platform tiktok --max-pages 10 --concurrency 2
    python scripts/crawl_user_videos.py --platform tiktok --dry-run        # 只解析不入库
    python scripts/crawl_user_videos.py --user-list users.txt --download --download-concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "app"))

import httpx
from common.logging import get_logger
from core.config import SchedulerConfig
from core.constants import DATATYPE_TO_MODEL
from filter import Bloom
from go_rpc import RpcClient
from models.user import User
from parser import general_parser
from pipeline import CrawlerPipeline
from services.video_download import VideoDownloadService
from sqlalchemy import select
from storage import MinioDB, SQLAlchemyDB

logger = get_logger(__file__)


def _to_models(parsed_items: list[dict]) -> list:
    """dict -> ORM 实例，仅保留模型表中存在的列，避免 wire 字段（如 url）引发 TypeError。"""
    models = []
    for item in parsed_items:
        model_cls = DATATYPE_TO_MODEL.get(item.get("datatype"))
        if not model_cls:
            logger.warning("未知 datatype: %s，跳过", item.get("datatype"))
            continue
        valid_cols = {c.name for c in model_cls.__table__.columns}
        clean = {k: v for k, v in item.items() if k in valid_cols}
        # TikTok 头像签名 URL 常超过 varchar(255)，列宽不足时截断（完整 URL 已存于 extend）
        if len(clean.get("avatar") or "") > 255:
            clean["avatar"] = clean["avatar"][:255]
        models.append(model_cls(**clean))
    return models


def extract_secuid(user: User) -> str | None:
    """从 User.extend（getUserInfo 写入的 userInfo JSON）中解析 secuid。

    getUserInfo 解析器将 data["userInfo"] 原样存入 extend，结构为
    {"user": {"secUid": "...", ...}, "stats": {...}}。
    若 extend 缺失或不含 secUid，返回 None（调用方应跳过该用户）。
    """
    ext = getattr(user, "extend", None)
    if not ext:
        return None
    try:
        data = json.loads(ext)
    except (json.JSONDecodeError, TypeError):
        return None
    return extract_secuid_from_data(data)


def extract_secuid_from_data(data: Any) -> str | None:
    """从 getUserInfo 响应体（或其 JSON 反序列化结果）中解析 secuid。

    兼容三种形态：{"user": {"secUid": ...}}、{"userInfo": {"user": {...}}}、
    以及被再包一层的情况。
    """
    if not isinstance(data, dict):
        return None
    ui = data.get("userInfo", data)
    if not isinstance(ui, dict):
        return None
    u = ui.get("user", {})
    if isinstance(u, dict):
        sec = u.get("secUid") or u.get("secuid")
        if sec:
            return str(sec)
    return None


async def fetch_user_info(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    platform: str,
    identifier: str,
    *,
    user_param: str,
    dry_run: bool,
) -> str | None:
    """调用 getUserInfo 抓取用户资料，解析后经 Pipeline 入库，并返回 secuid。

    Args:
        identifier: 用户标识（uniqueId / userId 等，go-rpc 侧参数名由 user_param 决定）。
        user_param: getUserInfo 的 RPC 参数名，默认 uniqueId。
        dry_run: 只解析不入库。

    Returns:
        secuid（供 getUserVideo 使用）；解析失败或缺少 secuid 时返回 None。
    """
    raw = await rpc.invoke(platform, "getUserInfo", {user_param: identifier})
    if not isinstance(raw, dict):
        logger.warning("用户 %s getUserInfo 返回非 dict，跳过", identifier)
        return None

    parsed = list(general_parser.parse(platform, raw, "getUserInfo", as_dto=False))
    if not dry_run and parsed:
        models = _to_models(parsed)
        if models:
            stats = await pipeline.process_items(models)
            logger.debug(
                "用户 %s getUserInfo 入库: inserted=%d updated=%d",
                identifier,
                stats["inserted"],
                stats["updated"],
            )
    else:
        logger.debug(
            "用户 %s getUserInfo 解析到 %d 条 (dry_run=%s)",
            identifier,
            len(parsed),
            dry_run,
        )

    # 返回的 userInfo 结构为 {"stats": ..., "statsV2": ..., "user": {"secUid": ...}}，
    # extract_secuid_from_data 兼容带/不带 userInfo 包装的形态
    return extract_secuid_from_data(raw)


def read_user_list(path: str | Path) -> list[str]:
    """读取用户列表文件（每行一个标识，忽略空行与 # 注释）。"""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    ids = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    if not ids:
        raise RuntimeError(f"用户列表文件为空：{path}")
    return ids


def _parse_extend(item: dict) -> dict:
    """解析 content item 的 extend JSON（非 dict 或解析失败时返回空 dict）。"""
    raw_ext = item.get("extend") or ""
    if isinstance(raw_ext, str):
        try:
            parsed_ext = json.loads(raw_ext)
            if isinstance(parsed_ext, dict):
                return parsed_ext
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _media_urls_from_extend(ext: dict, item: dict) -> tuple[str, str, str]:
    """从 extend 提取 (video_url, music_url, pic_url)；封面回退到顶层的 pic 字段。"""
    video_url = str(ext.get("video_url") or "")
    music_url = str(ext.get("music_url") or "")
    pic_url = str(ext.get("pic_url") or item.get("pic") or "")
    return video_url, music_url, pic_url


async def download_item_media(
    download_service: VideoDownloadService,
    platform: str,
    item: dict,
    download_sem: asyncio.Semaphore,
) -> bool:
    """下载单条内容的视频/音频/封面并上传 MinIO，成功后回写 item 的 extend 与 is_download。

    Returns:
        是否成功下载（成功时 item 被就地修改；失败仅记日志，不影响入库）
    """
    if item.get("datatype") != "content":
        return False
    content_id = item.get("content_id")
    if not content_id:
        return False
    ext = _parse_extend(item)
    video_url, music_url, pic_url = _media_urls_from_extend(ext, item)
    if not video_url:
        logger.debug("content %s 缺少 video_url，跳过下载", content_id)
        return False
    try:
        async with download_sem:
            if music_url and pic_url:
                video_res, audio_res, cover_res = await download_service.download_media(
                    video_url,
                    music_url,
                    pic_url,
                    platform,
                    content_id,
                )
            else:
                video_res = await download_service.download(
                    video_url, platform, content_id
                )
                audio_res = None
                cover_res = None
    except Exception as exc:
        logger.warning("content %s 媒体下载失败: %s", content_id, exc)
        return False

    # 回写 extend（保留原字段并附加 minio 对象名）与 is_download 标志
    ext["minio_video"] = video_res.object_name
    if audio_res is not None:
        ext["minio_audio"] = audio_res.object_name
    if cover_res is not None:
        ext["minio_pic"] = cover_res.object_name
    item["extend"] = json.dumps(ext, ensure_ascii=False)
    item["is_download"] = True
    return True


def _next_cursor(raw: dict, current: int) -> int | None:
    """从分页响应中提取下一页游标。

    TikTok 帖子列表接口一般返回 maxCursor；部分接口返回 cursor。
    优先 maxCursor，回退 cursor。若两者都缺失或与当前游标相同，返回 None 表示停止。
    """
    nxt = raw.get("maxCursor")
    if nxt is None:
        nxt = raw.get("cursor")
    if nxt is None:
        return None
    try:
        nxt = int(nxt)
    except (TypeError, ValueError):
        return None
    return None if nxt == current else nxt


async def crawl_user_videos(
    rpc: RpcClient,
    pipeline: CrawlerPipeline,
    platform: str,
    secuid: str,
    *,
    rps: float,
    max_pages: int,
    dry_run: bool,
    download_service: VideoDownloadService | None = None,
    download_sem: asyncio.Semaphore | None = None,
) -> tuple[int, int, int, int]:
    """分页抓取单个用户的视频列表，可选下载媒体。

    Returns:
        (pages, items, downloaded, failed) —— 抓取的页数、解析出的条目数、
        成功下载的媒体数、下载失败的媒体数。
    """
    pages, items, downloaded, failed = 0, 0, 0, 0
    if download_service is not None and download_sem is None:
        download_sem = asyncio.Semaphore(2)
    cursor = 0
    while True:
        raw = await rpc.invoke(
            platform, "getUserVideo", {"secuid": secuid, "cursor": cursor}
        )
        if not isinstance(raw, dict) or not raw.get("itemList"):
            break

        parsed = list(general_parser.parse(platform, raw, "getUserVideo", as_dto=False))
        if parsed:
            items += len(parsed)
            if download_service is not None and not dry_run:
                results = await asyncio.gather(
                    *(
                        download_item_media(
                            download_service, platform, item, download_sem
                        )
                        for item in parsed
                        if item.get("datatype") == "content"
                    )
                )
                downloaded += sum(1 for ok in results if ok)
                failed += len(results) - sum(1 for ok in results if ok)
            if not dry_run:
                models = _to_models(parsed)
                if models:
                    stats = await pipeline.process_items(models)
                    logger.debug(
                        "secuid=%s page=%d parsed=%d inserted=%d updated=%d downloaded=%d",
                        secuid,
                        pages + 1,
                        len(parsed),
                        stats["inserted"],
                        stats["updated"],
                        downloaded,
                    )
            else:
                logger.debug(
                    "secuid=%s page=%d parsed=%d (dry-run)",
                    secuid,
                    pages + 1,
                    len(parsed),
                )

        pages += 1
        if max_pages and pages >= max_pages:
            logger.debug(
                "secuid=%s 已达 max_pages=%d 上限，停止翻页", secuid, max_pages
            )
            break

        has_more = raw.get("hasMore")
        if has_more is False:
            break
        nxt = _next_cursor(raw, cursor)
        if nxt is None:
            break
        cursor = nxt

        if rps > 0:
            await asyncio.sleep(1.0 / rps)

    return pages, items, downloaded, failed


def _build_download_service(
    config: SchedulerConfig,
    *,
    platform: str,
    bucket: str,
    no_proxy: bool,
) -> tuple[MinioDB, httpx.AsyncClient, VideoDownloadService]:
    """按配置组装 MinIO 与下载服务（download_media 上传到 bucket=platform）。

    bucket 为默认桶（与 Worker registry 约定一致，均为 "videos"）；媒体实际
    上传到按平台命名的桶（platform），对象名 {content_id}/video|audio|pic。
    """
    minio_cfg = config.minio
    minio = MinioDB(
        endpoint=f"{minio_cfg.host}:{minio_cfg.port}",
        access_key=minio_cfg.username,
        secret_key=minio_cfg.password,
        secure=minio_cfg.secure,
        amode=True,
    )
    proxy_url = "" if no_proxy else config.proxy.url
    client = httpx.AsyncClient(
        proxy=proxy_url or None,
        trust_env=False,
        follow_redirects=True,
        timeout=httpx.Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
        headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
    )
    service = VideoDownloadService(
        client,
        minio,
        bucket,
        cover_bucket=platform,
        audio_bucket=platform,
        proxy_url=proxy_url,
    )
    return minio, client, service


async def run(
    platform: str,
    config_path: str,
    *,
    limit: int,
    offset: int,
    max_pages: int,
    concurrency: int,
    rps: float,
    require_secuid: bool,
    dry_run: bool,
    user_list: str | None = None,
    user_param: str = "username",
    download: bool = False,
    bucket: str = "videos",
    no_proxy: bool = False,
    download_concurrency: int = 2,
) -> None:
    config = SchedulerConfig.from_toml(config_path)
    pg = config.postgresql

    # 脚本级速率上限；--rps 未指定时退化为固定 1.0（如需与 Worker 一致可接入
    # SiteSource.load_active_quotas 读取平台配额）。翻页与用户间均按此速率休眠。
    if rps <= 0:
        rps = 1.0

    db = SQLAlchemyDB(
        username=pg.username,
        password=pg.password,
        host=pg.host,
        port=pg.port,
        database=pg.database,
        amode=True,
        driver="postgresql",
    )
    await db.aconnect()
    await db.ainit_db()

    bloom = Bloom(redis_url=config.redis.url, amode=True)
    pipeline = CrawlerPipeline(filter=bloom, store=db)
    rpc = RpcClient(
        base_url=config.rpc_base_url, token=config.rpc_token, timeout=config.rpc_timeout
    )

    minio = download_client = download_service = None
    if download:
        minio, download_client, download_service = _build_download_service(
            config,
            platform=platform,
            bucket=bucket,
            no_proxy=no_proxy,
        )
        await minio.amake_bucket(platform)

    download_sem = asyncio.Semaphore(max(1, download_concurrency))
    sem = asyncio.Semaphore(max(1, concurrency))
    total_pages, total_items = 0, 0
    total_downloaded, download_failed = 0, 0
    skipped, errors = 0, 0
    total_users = 0

    async def _worker(user: User) -> None:
        nonlocal \
            total_pages, \
            total_items, \
            total_downloaded, \
            download_failed, \
            skipped, \
            errors
        secuid = extract_secuid(user)
        if not secuid:
            if require_secuid:
                logger.warning(
                    "用户 %s (user_id=%s) 缺少 secuid，跳过",
                    user.username or "-",
                    user.user_id,
                )
                skipped += 1
                return
            secuid = user.username or user.user_id or ""
        try:
            pages, items, dl_ok, dl_fail = await crawl_user_videos(
                rpc,
                pipeline,
                platform,
                secuid,
                rps=rps,
                max_pages=max_pages,
                dry_run=dry_run,
                download_service=download_service,
                download_sem=download_sem,
            )
            total_pages += pages
            total_items += items
            total_downloaded += dl_ok
            download_failed += dl_fail
            logger.info(
                "用户 %s 抓取完成: pages=%d items=%d downloaded=%d failed=%d",
                user.username or user.user_id,
                pages,
                items,
                dl_ok,
                dl_fail,
            )
        except Exception as e:
            errors += 1
            logger.error("用户 %s 抓取失败: %s", user.username or user.user_id, e)

    async def _worker_from_list(identifier: str) -> None:
        nonlocal \
            total_pages, \
            total_items, \
            total_downloaded, \
            download_failed, \
            skipped, \
            errors
        secuid = await fetch_user_info(
            rpc,
            pipeline,
            platform,
            identifier,
            user_param=user_param,
            dry_run=dry_run,
        )
        if not secuid:
            if require_secuid:
                logger.warning("用户 %s 未解析出 secuid，跳过", identifier)
                skipped += 1
                return
            secuid = identifier
        try:
            pages, items, dl_ok, dl_fail = await crawl_user_videos(
                rpc,
                pipeline,
                platform,
                secuid,
                rps=rps,
                max_pages=max_pages,
                dry_run=dry_run,
                download_service=download_service,
                download_sem=download_sem,
            )
            total_pages += pages
            total_items += items
            total_downloaded += dl_ok
            download_failed += dl_fail
            logger.info(
                "用户 %s 抓取完成: pages=%d items=%d downloaded=%d failed=%d",
                identifier,
                pages,
                items,
                dl_ok,
                dl_fail,
            )
        except Exception as e:
            errors += 1
            logger.error("用户 %s 抓取失败: %s", identifier, e)

    try:
        if user_list:
            identifiers = read_user_list(user_list)
            total_users = len(identifiers)
            logger.info("从 %s 读取到 %d 个用户", user_list, total_users)

            async def _guarded_identifier(identifier: str) -> None:
                async with sem:
                    await _worker_from_list(identifier)

            await asyncio.gather(*(_guarded_identifier(x) for x in identifiers))
        else:
            async with db.asession_scope() as session:
                stmt = select(User).where(User.platform == platform)
                if limit:
                    stmt = stmt.limit(limit)
                if offset:
                    stmt = stmt.offset(offset)
                stmt = stmt.order_by(User.id.asc())
                rows = (await session.execute(stmt)).scalars().all()
            logger.info("查询到 %d 个 %s 用户", len(rows), platform)
            total_users = len(rows)
            if not rows:
                logger.info("无用户可抓取，退出")
                return

            async def _guarded(u: User) -> None:
                async with sem:
                    await _worker(u)

            await asyncio.gather(*(_guarded(u) for u in rows))
    finally:
        logger.info(
            "汇总: users=%d pages=%d items=%d downloaded=%d fail_download=%d skipped=%d errors=%d (dry_run=%s)",
            total_users,
            total_pages,
            total_items,
            total_downloaded,
            download_failed,
            skipped,
            errors,
            dry_run,
        )
        await rpc.close()
        await pipeline.close()
        await bloom.aclose()
        if download_service is not None:
            await download_client.aclose()
            await minio.aclose()
        await db.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="遍历用户分页抓取视频 (getUserInfo + getUserVideo)，可下载媒体到 MinIO"
    )
    ap.add_argument("--platform", default="tiktok", help="平台标识，默认 tiktok")
    ap.add_argument("--config", default="config.toml", help="配置文件路径")
    ap.add_argument("--limit", type=int, default=0, help="最多处理用户数，0=全部")
    ap.add_argument("--offset", type=int, default=0, help="用户列表偏移量（用于分批）")
    ap.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="单用户最大翻页数，0=不限（依赖 hasMore）",
    )
    ap.add_argument("--concurrency", type=int, default=1, help="并发用户数")
    ap.add_argument(
        "--rps", type=float, default=0.0, help="每用户 RPC 速率上限，0=默认 1.0"
    )
    ap.add_argument(
        "--no-require-secuid",
        dest="require_secuid",
        action="store_false",
        help="secuid 缺失时不跳过（尝试用 username/user_id 兜底）",
    )
    ap.add_argument(
        "--user-list",
        default=None,
        help="用户列表文件（每行一个 TikTok 用户标识），提供后不查 t_busi_user",
    )
    ap.add_argument(
        "--user-param",
        default="username",
        help="getUserInfo 的 RPC 参数名（go-rpc 代理定义），默认 username（TikTok uniqueId）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只解析不入库")
    ap.add_argument(
        "--download", action="store_true", help="下载视频/音频/封面到 MinIO"
    )
    ap.add_argument(
        "--bucket", default="videos", help="MinIO 默认 bucket（服务内部按平台再建桶）"
    )
    ap.add_argument(
        "--no-proxy", action="store_true", help="下载时绕过 config.toml 代理"
    )
    ap.add_argument(
        "--download-concurrency", type=int, default=2, help="下载媒体并发数"
    )
    args = ap.parse_args()

    asyncio.run(
        run(
            platform=args.platform,
            config_path=args.config,
            limit=args.limit,
            offset=args.offset,
            max_pages=args.max_pages,
            concurrency=args.concurrency,
            rps=args.rps,
            require_secuid=args.require_secuid,
            dry_run=args.dry_run,
            user_list=args.user_list,
            user_param=args.user_param,
            download=args.download,
            bucket=args.bucket,
            no_proxy=args.no_proxy,
            download_concurrency=args.download_concurrency,
        )
    )


if __name__ == "__main__":
    main()
