"""将 MinIO 媒体对象迁移到 {platform}/{content_id}/{kind} 布局。"""
from __future__ import annotations

import argparse
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from minio import Minio
from minio.commonconfig import CopySource


@dataclass(frozen=True)
class Migration:
    source_bucket: str
    target_bucket: str
    source: str
    target: str


def _same_content(source_stat, target_stat) -> bool:
    source_etag = getattr(source_stat, "etag", None)
    return bool(
        source_stat.size == target_stat.size
        and source_etag
        and source_etag == getattr(target_stat, "etag", None)
    )


def target_object_name(bucket: str, object_name: str) -> tuple[str, str] | None:
    parts = PurePosixPath(object_name).parts
    if len(parts) < 2:
        return None
    platform = parts[0]

    if bucket == "videos" and len(parts) == 2:
        content_id = PurePosixPath(parts[1]).stem
        return platform, f"{content_id}/video"
    if bucket == "audios" and len(parts) == 3 and parts[1] == "audio":
        content_id = PurePosixPath(parts[2]).stem
        return platform, f"{content_id}/audio"
    if bucket == "images" and len(parts) == 3 and parts[1] == "pic":
        content_id = PurePosixPath(parts[2]).stem
        return platform, f"{content_id}/pic"
    return None


def build_plan(client: Minio) -> list[Migration]:
    plan = []
    targets: dict[tuple[str, str], tuple[str, str]] = {}
    for bucket in ("videos", "audios", "images"):
        if not client.bucket_exists(bucket):
            continue
        for item in client.list_objects(bucket, recursive=True):
            target = target_object_name(bucket, item.object_name)
            if target:
                target_bucket, target_name = target
                target_key = (target_bucket, target_name)
                source_key = (bucket, item.object_name)
                previous_source = targets.get(target_key)
                if previous_source is not None and previous_source != source_key:
                    raise RuntimeError(
                        f"多个源对象映射到同一目标：{target_bucket}/{target_name}"
                    )
                targets[target_key] = source_key
                plan.append(Migration(bucket, target_bucket, item.object_name, target_name))
    return plan


def migrate(client: Minio, plan: list[Migration], *, delete_source: bool) -> tuple[int, int]:
    migrated = skipped = 0
    for item in plan:
        source_stat = client.stat_object(item.source_bucket, item.source)
        if not client.bucket_exists(item.target_bucket):
            client.make_bucket(item.target_bucket)
        try:
            target_stat = client.stat_object(item.target_bucket, item.target)
        except Exception as exc:
            if getattr(exc, "code", None) not in {"NoSuchKey", "NoSuchObject"}:
                raise
        else:
            if not _same_content(source_stat, target_stat):
                raise RuntimeError(
                    f"目标对象冲突：{item.target_bucket}/{item.target} 与源对象内容不同"
                )
            if delete_source:
                client.remove_object(item.source_bucket, item.source)
            skipped += 1
            continue

        client.copy_object(
            item.target_bucket,
            item.target,
            CopySource(item.source_bucket, item.source),
        )
        target_stat = client.stat_object(item.target_bucket, item.target)
        if not _same_content(source_stat, target_stat):
            raise RuntimeError(f"复制校验失败：{item.source_bucket}/{item.source}")
        if delete_source:
            client.remove_object(item.source_bucket, item.source)
        migrated += 1
    return migrated, skipped


def load_client(config_path: str) -> Minio:
    with open(config_path, "rb") as file:
        config = tomllib.load(file)["minio"]
    return Minio(
        f"{config['host']}:{config['port']}",
        access_key=config["username"],
        secret_key=config["password"],
        secure=bool(config.get("secure", False)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 MinIO 媒体对象目录结构")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--apply", action="store_true", help="执行服务端复制")
    parser.add_argument(
        "--delete-source", action="store_true", help="校验复制成功后删除旧对象"
    )
    args = parser.parse_args()
    if args.delete_source and not args.apply:
        parser.error("--delete-source 必须与 --apply 一起使用")

    client = load_client(args.config)
    plan = build_plan(client)
    print(f"待迁移对象：{len(plan)}")
    for item in plan[:20]:
        print(
            f"{item.source_bucket}/{item.source} -> "
            f"{item.target_bucket}/{item.target}"
        )
    if len(plan) > 20:
        print(f"其余 {len(plan) - 20} 个对象省略")
    if not args.apply:
        print("当前为预览模式；使用 --apply 执行复制")
        return

    migrated, skipped = migrate(client, plan, delete_source=args.delete_source)
    print(f"迁移完成：copied={migrated} existing={skipped} deleted={args.delete_source}")


if __name__ == "__main__":
    main()
