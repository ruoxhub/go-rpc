"""Download a uniquely identified video object from MinIO."""

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from services.video_download.naming import (
    encode_object_segment,
    video_object_name,
    video_object_stem,
)


_SAFE_SUFFIX = re.compile(r"\.[A-Za-z0-9]{1,10}\Z")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class VideoObjectNotFoundError(LookupError):
    """No usable video object exists for the requested content."""


class AmbiguousVideoObjectError(LookupError):
    """More than one video object exists for the requested content."""


@dataclass(frozen=True)
class DownloadedMinioVideo:
    object_name: str
    local_path: Path
    bucket: str


class MinioVideoSource:
    def __init__(self, minio: Any, bucket: str):
        self._minio = minio
        self.bucket = bucket

    async def download(
        self, *, platform: str, content_id: str, target_dir: Path
    ) -> DownloadedMinioVideo:
        encode_object_segment(platform, "platform")
        prefix = video_object_name(content_id)
        bucket = encode_object_segment(platform, "platform")

        safe_local_id = "".join(
            char if char.isalnum() or char in "-_" else "_"
            for char in content_id
        )
        if not safe_local_id:
            safe_local_id = "video"

        async def _find_matches(object_stem: str) -> list[str]:
            objects = await self._minio.alist_objects(
                bucket, prefix=object_stem, recursive=True
            )
            expected_path = PurePosixPath(object_stem)
            found = []
            for item in objects:
                object_name = getattr(item, "object_name", None)
                if not isinstance(object_name, str):
                    continue
                object_path = PurePosixPath(object_name)
                if (
                    object_path.parent == expected_path.parent
                    and object_path.stem == expected_path.name
                ):
                    found.append(object_name)
            return found

        matches = await _find_matches(prefix)
        if matches:
            object_bucket = bucket
        else:
            object_bucket = self.bucket
            bucket = self.bucket
        encoded_legacy_stem = video_object_stem(platform, content_id)
        if not matches:
            matches = await _find_matches(encoded_legacy_stem)
        legacy_stem = f"{platform}/{content_id}"
        legacy_safe = all(
            value
            and value not in {".", ".."}
            and "/" not in value
            and "\\" not in value
            for value in (platform, content_id)
        )
        if not matches and legacy_safe and legacy_stem != encoded_legacy_stem:
            matches = await _find_matches(legacy_stem)

        if not matches:
            raise VideoObjectNotFoundError(
                f"Video object not found for {platform}/{content_id}"
            )
        if len(matches) > 1:
            raise AmbiguousVideoObjectError(
                f"Multiple video objects found for {platform}/{content_id}"
            )

        object_name = matches[0]
        object_suffix = PurePosixPath(object_name).suffix
        suffix = object_suffix if _SAFE_SUFFIX.fullmatch(object_suffix) else ".video"
        local_stem = (
            f"_{safe_local_id}"
            if safe_local_id.upper() in _WINDOWS_RESERVED_NAMES
            else safe_local_id
        )
        target_path = Path(target_dir)
        target_path.mkdir(parents=True, exist_ok=True)
        local_path = target_path / f"{local_stem}{suffix}"

        temporary = tempfile.NamedTemporaryFile(
            delete=False, dir=target_path, suffix=".partial"
        )
        temporary_path = Path(temporary.name)
        temporary.close()
        sdk_temporary_path = temporary_path.with_suffix(
            f"{temporary_path.suffix}.minio"
        )
        sdk_temporary_path.unlink(missing_ok=True)
        try:
            await self._minio.afget_object(
                object_bucket,
                object_name,
                str(temporary_path),
                tmp_file_path=str(sdk_temporary_path),
            )
            if (
                not temporary_path.is_file()
                or temporary_path.stat().st_size == 0
            ):
                raise VideoObjectNotFoundError(
                    f"Downloaded video is missing or empty for {platform}/{content_id}"
                )
            os.replace(temporary_path, local_path)
        finally:
            temporary_path.unlink(missing_ok=True)
            sdk_temporary_path.unlink(missing_ok=True)

        return DownloadedMinioVideo(object_name, local_path, object_bucket)
