"""下载视频并上传到 MinIO。

示例：
    python scripts/download_video_input_minio.py
    python scripts/download_video_input_minio.py --url "https://example.com/video.mp4"
    python scripts/download_video_input_minio.py --bucket videos --object-name tiktok/123.mp4
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from services.video_download import VideoDownloadService
from storage import MinioDB


DEFAULT_VIDEO_URL = (
    "https://www.tiktok.com/aweme/v1/play/?faid=1988&file_id=7cbbb86f3a804e8f96573346ef91dcf8&is_play_url=1&item_id=7667357497631526174&line=0&ply_type=2&signaturev3=dmlkZW9faWQ7ZmlsZV9pZDtpdGVtX2lkLjQwYTFkMThjNzgxOGYxNjA5NTZiYTI5M2RlNTBlYjFm&tk=tt_chain_token&video_id=v15025gf0000d9juqufog65ou2cup7l0"
)


def _load_config(config_path: Path) -> tuple[dict, str | None]:
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    if "minio" not in config:
        raise ValueError(f"配置文件缺少 [minio]：{config_path}")
    return config["minio"], config.get("proxy", {}).get("url")


def _derive_content_id(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    identity = query.get("item_id", query.get("video_id", []))
    return identity[0] if identity else Path(parsed.path).stem or hashlib.sha256(url.encode()).hexdigest()[:16]


def download_and_upload(
    *,
    url: str,
    minio: MinioDB,
    bucket: str,
    object_name: str | None,
    proxy: str | None,
) -> str:
    """通过公共服务流式下载并上传到 MinIO，返回对象名。"""
    async def _run() -> str:
        async with httpx.AsyncClient(
            proxy=proxy,
            trust_env=False,
            follow_redirects=True,
            timeout=httpx.Timeout(connect=15, read=300, write=30, pool=15),
            headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
        ) as client:
            result = await VideoDownloadService(client, minio, bucket).download(
                url,
                "",
                _derive_content_id(url),
                object_name=object_name,
            )
            return result.object_name

    return asyncio.run(_run())


def main() -> None:
    parser = argparse.ArgumentParser(description="下载视频并上传到 MinIO")
    parser.add_argument("--url", default=DEFAULT_VIDEO_URL, help="视频下载地址")
    parser.add_argument("--config", type=Path, default=Path("config.toml"), help="配置文件")
    parser.add_argument("--bucket", default="videos", help="MinIO bucket，默认 videos")
    parser.add_argument("--object-name", help="MinIO 对象名，默认从视频 URL 生成")
    parser.add_argument("--no-proxy", action="store_true", help="忽略 config.toml 中的代理")
    parser.add_argument("--secure", action="store_true", help="使用 HTTPS 连接 MinIO")
    args = parser.parse_args()

    config, configured_proxy = _load_config(args.config)
    endpoint = f"{config['host']}:{config['port']}"
    minio = MinioDB(
        endpoint=endpoint,
        access_key=config["username"],
        secret_key=config["password"],
        secure=args.secure,
    )
    minio.make_bucket(args.bucket)
    object_name = download_and_upload(
        url=args.url,
        minio=minio,
        bucket=args.bucket,
        object_name=args.object_name,
        proxy=None if args.no_proxy else configured_proxy,
    )
    print(f"上传成功：{args.bucket}/{object_name}")


if __name__ == "__main__":
    main()
