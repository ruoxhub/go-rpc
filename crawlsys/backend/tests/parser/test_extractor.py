"""Tests for WebExtractor and convenience functions."""

from parser.extractor import (
    Metadata,
    WebExtractor,
    extract_metadata,
    generate_markdown,
)


def test_metadata_dataclass():
    meta = Metadata(title="Test", url="https://example.com/article")
    assert meta.title == "Test"
    assert meta.url == "https://example.com/article"
    data = meta.to_dict()
    assert isinstance(data, dict)
    assert data["title"] == "Test"


def test_web_extractor_basic_extraction():
    html = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <title>页面标题 - 站点名</title>
        <meta name="description" content="这是一篇测试文章描述">
        <meta name="author" content="测试作者">
        <meta property="og:site_name" content="测试站点">
        <meta property="og:image" content="/images/cover.jpg">
        <link rel="icon" href="/favicon.png">
        <link rel="canonical" href="https://example.com/posts/1">
    </head>
    <body>
        <article>
            <h1>文章主标题</h1>
            <p>这里是正文段落内容，用于测试正文提取与字数统计。</p>
        </article>
    </body>
    </html>
    """
    extractor = WebExtractor(html, url="https://example.com/posts/1")
    meta = extractor.extract()

    assert meta.title == "页面标题 - 站点名"
    assert meta.description == "这是一篇测试文章描述"
    assert meta.author == "测试作者"
    assert meta.site == "测试站点"
    assert meta.image == "https://example.com/images/cover.jpg"
    assert meta.favicon == "https://example.com/favicon.png"
    assert meta.language == "zh-CN"
    assert meta.domain == "example.com"
    assert meta.url == "https://example.com/posts/1"
    assert "这里是正文段落内容" in meta.content
    assert meta.word_count > 0


def test_web_extractor_with_custom_selectors():
    html = """
    <html>
    <body>
        <div class="my-title">自定义标题</div>
        <div class="my-author">自定义作者</div>
        <span class="pub-time">2026-08-15 12:00:00</span>
        <div class="main-body">这是自定义选择器提取的正文。</div>
    </body>
    </html>
    """
    selectors = {
        "title": ".my-title",
        "author": ".my-author",
        "published": ".pub-time",
        "content": ".main-body",
    }
    extractor = WebExtractor(html, url="https://example.com", selectors=selectors)
    meta = extractor.extract()

    assert meta.title == "自定义标题"
    assert meta.author == "自定义作者"
    assert meta.published == "2026-08-15 12:00:00"
    assert meta.content == "这是自定义选择器提取的正文。"


def test_web_extractor_opengraph_priority():
    html = """
    <html>
    <head>
        <title>原标题</title>
        <meta property="og:title" content="OG标题">
        <meta property="og:description" content="OG描述">
        <meta name="description" content="Meta描述">
    </head>
    <body>
        <p>正文</p>
    </body>
    </html>
    """
    meta = extract_metadata(html, "https://example.com")
    assert meta.title == "OG标题"
    assert meta.description == "OG描述"


def test_web_extractor_to_markdown():
    html = """
    <html>
    <head>
        <title>测试 Markdown</title>
        <meta name="author" content="张三">
        <meta name="description" content="这是摘要说明">
    </head>
    <body>
        <article>
            <p>这是第一段文字。</p>
        </article>
    </body>
    </html>
    """
    md = generate_markdown(html, "https://example.com/news/1", tags=["tech", "ai"])
    assert 'title: "测试 Markdown"' in md
    assert 'source: "https://example.com/news/1"' in md
    assert '- "[[张三]]"' in md
    assert '- "tech"' in md
    assert '- "ai"' in md
    assert "这是第一段文字。" in md


def test_web_extractor_to_content_model():
    html = """
    <html>
    <head>
        <title>文章标题</title>
        <meta name="author" content="李四">
    </head>
    <body>
        <article>
            <p>文章内容详情</p>
        </article>
    </body>
    </html>
    """
    extractor = WebExtractor(html, url="https://example.com/article/100")
    content = extractor.to_content_model(platform="custom_web", data_type="4")
    assert content.title == "文章标题"
    assert content.author == "李四"
    assert content.platform == "custom_web"
    assert content.data_type == "4"
    assert content.url == "https://example.com/article/100"
    assert "文章内容详情" in content.content
