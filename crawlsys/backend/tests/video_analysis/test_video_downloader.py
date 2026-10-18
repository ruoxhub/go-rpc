from pathlib import Path

import pytest

import tools.video_downloader as video_downloader


class _Response:
    def __init__(self, chunks: list[bytes], content_type: str) -> None:
        self.chunks = chunks
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    def iter_bytes(self, chunk_size: int):
        assert chunk_size == 1 << 16
        yield from self.chunks


class _Client:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        pass

    def stream(self, method: str, url: str):
        assert method == "GET"
        suffix = Path(url).suffix
        content_types = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".jpg": "image/jpeg",
        }
        return _Response([url.rsplit("/", 1)[-1].encode()], content_types[suffix])


def test_download_media_downloads_video_audio_and_cover(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(video_downloader, "Client", _Client)

    result = video_downloader.download_media(
        tmp_path,
        content_id="123",
        video_url="https://cdn.example.com/video.mp4",
        music_url="https://cdn.example.com/audio.mp3",
        pic_url="https://cdn.example.com/cover.jpg",
    )

    assert result.video_path == (tmp_path / "123.mp4").resolve()
    assert result.video_path.read_bytes() == b"video.mp4"
    assert (tmp_path / "123.mp3").read_bytes() == b"audio.mp3"
    assert (tmp_path / "123.jpg").read_bytes() == b"cover.jpg"
    assert result.title == "123"
    assert result.duration_seconds is None


def test_download_media_rejects_empty_video_download(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class EmptyClient(_Client):
        def stream(self, method: str, url: str):
            return _Response([], "video/mp4")

    monkeypatch.setattr(video_downloader, "Client", EmptyClient)

    try:
        video_downloader.download_media(
            tmp_path,
            content_id="123",
            video_url="https://cdn.example.com/video.mp4",
        )
    except RuntimeError as error:
        assert str(error) == "下载完成但输出视频为空。"
    else:
        raise AssertionError("应拒绝空视频文件")

    assert not (tmp_path / "123.mp4").exists()


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("text/html", b"<html>access denied</html>"),
        ("application/xml", b"<?xml version='1.0'?><Error>denied</Error>"),
    ],
)
def test_download_media_rejects_error_page_with_http_200(
    monkeypatch,
    tmp_path: Path,
    content_type: str,
    body: bytes,
) -> None:
    class HtmlClient(_Client):
        def stream(self, method: str, url: str):
            return _Response([body], content_type)

    monkeypatch.setattr(video_downloader, "Client", HtmlClient)

    try:
        video_downloader.download_media(
            tmp_path,
            content_id="123",
            video_url="https://cdn.example.com/video.mp4",
        )
    except RuntimeError as error:
        assert "不是有效视频" in str(error)
    else:
        raise AssertionError("应拒绝 HTTP 200 的 HTML 错误页面")

    assert not any(tmp_path.iterdir())


def test_download_media_accepts_octet_stream_with_media_signature(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class BinaryClient(_Client):
        def stream(self, method: str, url: str):
            return _Response([b"\x00\x00\x00\x18ftypisomvideo"], "application/octet-stream")

    monkeypatch.setattr(video_downloader, "Client", BinaryClient)

    result = video_downloader.download_media(
        tmp_path,
        content_id="123",
        video_url="https://cdn.example.com/video",
    )

    assert result.video_path.suffix == ".mp4"


def test_download_media_uses_detected_response_formats(monkeypatch, tmp_path: Path) -> None:
    class TypedClient(_Client):
        def stream(self, method: str, url: str):
            if "video" in url:
                return _Response([b"video"], "video/webm")
            if "audio" in url:
                return _Response([b"audio"], "audio/webm")
            return _Response([b"image"], "image/png")

    monkeypatch.setattr(video_downloader, "Client", TypedClient)

    result = video_downloader.download_media(
        tmp_path,
        content_id="123",
        video_url="https://cdn.example.com/video",
        music_url="https://cdn.example.com/audio",
        pic_url="https://cdn.example.com/cover",
    )

    assert result.video_path.suffix == ".webm"
    assert result.audio_path.suffix == ".webm"
    assert result.audio_path != result.video_path
    assert result.cover_path.suffix == ".png"


def test_download_media_accepts_tiktok_audio_reported_as_video_mp4(
    monkeypatch, tmp_path: Path
) -> None:
    class TikTokClient(_Client):
        def stream(self, method: str, url: str):
            if "music" in url:
                return _Response([b"\x00\x00\x00\x18ftypM4A audio"], "video/mp4")
            return super().stream(method, url)

    monkeypatch.setattr(video_downloader, "Client", TikTokClient)

    result = video_downloader.download_media(
        tmp_path,
        content_id="123",
        video_url="https://cdn.example.com/video.mp4",
        music_url="https://music.example.com/audio?signature=secret",
    )

    assert result.audio_path.suffix == ".m4a"


def test_download_media_accepts_tiktok_mp3_reported_as_video_mp4(
    monkeypatch, tmp_path: Path
) -> None:
    class TikTokClient(_Client):
        def stream(self, method: str, url: str):
            if "music" in url:
                return _Response([b"ID3\x04\x00\x00\x00\x00\x03\x60audio"], "video/mp4")
            return super().stream(method, url)

    monkeypatch.setattr(video_downloader, "Client", TikTokClient)

    result = video_downloader.download_media(
        tmp_path,
        content_id="123",
        video_url="https://cdn.example.com/video.mp4",
        music_url="https://music.example.com/audio",
    )

    assert result.audio_path.suffix == ".mp3"


def test_download_media_error_has_safe_response_diagnostics(
    monkeypatch, tmp_path: Path
) -> None:
    class ErrorClient(_Client):
        def stream(self, method: str, url: str):
            return _Response([b"<html>denied</html>"], "text/html")

    monkeypatch.setattr(video_downloader, "Client", ErrorClient)

    with pytest.raises(RuntimeError) as caught:
        video_downloader.download_media(
            tmp_path,
            content_id="123",
            video_url="https://cdn.example.com/video?signature=secret",
        )

    message = str(caught.value)
    assert "host=cdn.example.com" in message
    assert "content_type=text/html" in message
    assert "signature=3c68746d6c3e64656e696564" in message
    assert "signature=secret" not in message
