"""web_extractor.py - 网页元数据提取模块

从 HTML 中提取网页元数据，提取优先级：
Open Graph → Twitter Cards → Schema.org → HTML Meta → DOM

集成 Markdown 生成、内容提取、ORM 模型转换。
"""

import copy
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

__all__ = [
    "Metadata",
    "WebExtractor",
    "_WebExtractor",
    "MarkdownConverter",
    "extract_metadata",
    "extract_metadata_from_url",
    "generate_markdown",
]


@dataclass
class Metadata:
    """提取的网页元数据结构"""

    title: str = ""
    description: str = ""
    author: str = ""
    published: str = ""
    site: str = ""
    image: str = ""
    favicon: str = ""
    language: str = ""
    domain: str = ""
    url: str = ""
    word_count: int = 0
    schema_org_data: dict[str, Any] | None = None
    meta_tags: list[dict[str, str]] = field(default_factory=list)
    content: str = ""
    markdown: str = ""
    cleaned_html: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)


class MarkdownConverter:
    """Markdown 格式转换包装类，优先使用 markitdown，降级使用 HTML 文本解析"""

    def __init__(self) -> None:
        try:
            import importlib

            mod = importlib.import_module("markitdown.converters")
            self._converter = mod.HtmlConverter()
        except Exception:
            self._converter = None

    def convert(self, html: str, base_url: str = "") -> str:
        if self._converter is not None:
            try:
                res = self._converter.convert(html, base_url=base_url)
                return getattr(res, "text_content", str(res))
            except Exception as e:
                logger.debug("Markdown conversion error: %s", e)
        try:
            soup = BeautifulSoup(html, "html.parser")
            return soup.get_text(separator="\n", strip=True)
        except Exception as e:
            logger.debug("HTML fallback parse error: %s", e)
            return ""


class WebExtractor:
    """网页元数据提取器

    从 HTML 内容中提取丰富的元数据信息，包括标题、作者、描述、
    发布日期、站点信息、图片、图标、语言、字数统计、正文内容等。

    提取优先级：
        0. 自定义 CSS selector（如果通过 selectors 参数提供）
        1. Open Graph (og:*) 标签
        2. Twitter Cards (twitter:*) 标签
        3. Schema.org (JSON-LD / 微数据)
        4. HTML Meta 标签
        5. DOM 元素（标题、作者链接、byline 等）
    """

    MONTH_MAP = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }

    def __init__(
        self,
        html: str,
        url: str = "",
        parser: str = "lxml",
        selectors: dict[str, str] | None = None,
        content_format: str = "text",
        **kwargs: Any,
    ):
        """初始化提取器

        Args:
            html: HTML 字符串内容
            url: 页面完整 URL，用于解析相对路径链接
            parser: BeautifulSoup 解析器，默认 'lxml'
            selectors: 自定义 CSS 选择器字典，key 为字段名，value 为 CSS selector。
            content_format: 默认内容格式，支持 'text', 'html', 'markdown'
        """
        self.url = url or ""
        self.selectors = selectors or {}
        self.content_format = content_format
        try:
            self.soup = BeautifulSoup(html, parser)
        except Exception:
            self.soup = BeautifulSoup(html, "html.parser")
        self._schema_data: dict[str, Any] | None = None
        self._meta_tags_list: list[dict[str, str]] | None = None

    def _select_value(
        self,
        field: str,
        attr: str | None = None,
        resolve_url: bool = False,
    ) -> str:
        selector = self.selectors.get(field)
        if not selector:
            return ""

        el = self.soup.select_one(selector)
        if not el:
            return ""

        if attr:
            val = el.get(attr, "")
            value = " ".join(val).strip() if isinstance(val, list) else str(val).strip()
        else:
            value = el.get_text(strip=True)

        if resolve_url and value:
            value = self._resolve_url(value)

        return value

    def extract(self, *args: Any, **kwargs: Any) -> Metadata:
        """提取所有元数据并返回 Metadata 对象"""
        return Metadata(
            title=self._extract_title(),
            description=self._extract_description(),
            author=self._extract_author(),
            published=self._extract_published(),
            site=self._extract_site(),
            image=self._extract_image(),
            favicon=self._extract_favicon(),
            language=self._extract_language(),
            domain=self._extract_domain(),
            url=self._extract_url(),
            word_count=self._extract_word_count(),
            schema_org_data=self._extract_schema_org(),
            meta_tags=self._extract_meta_tags_list(),
            content=self._extract_content(format=self.content_format),
        )

    # ==================== 内部工具方法 ====================

    def _resolve_url(self, href: str) -> str:
        """解析相对 URL 为绝对 URL"""
        if not self.url or not href:
            return href
        if href.startswith(("http://", "https://", "//")):
            return href
        return urljoin(self.url, href)

    def _get_meta_content(self, fuzzy: bool = False, **kwargs: Any) -> str:
        """获取单个 meta 标签的 content 值"""
        query: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k == "attrs" and isinstance(v, dict):
                query.update(v)
            else:
                query[k] = v

        if not fuzzy:
            meta = self.soup.find("meta", attrs=query)
        else:

            def _match(tag: Tag) -> bool:
                if tag.name != "meta":
                    return False
                for qk, qv in query.items():
                    for attr_name, attr_val in tag.attrs.items():
                        if attr_name.lower() == qk.lower():
                            if isinstance(attr_val, list):
                                norm_val = " ".join(attr_val)
                            elif attr_val is None:
                                norm_val = ""
                            else:
                                norm_val = str(attr_val)
                            if str(qv).lower() in norm_val.lower():
                                return True
                return False

            meta = self.soup.find(_match)

        if meta and hasattr(meta, "get"):
            content = meta.get("content", "")
            if isinstance(content, list):
                return " ".join(content).strip()
            return str(content).strip() if content else ""
        return ""

    def _get_meta_contents(self, **kwargs: Any) -> list[str]:
        """获取所有匹配 meta 标签的 content 值列表"""
        query: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k == "attrs" and isinstance(v, dict):
                query.update(v)
            else:
                query[k] = v
        metas = self.soup.find_all("meta", attrs=query)
        results: list[str] = []
        for m in metas:
            if hasattr(m, "get"):
                content = m.get("content", "")
                val = (
                    " ".join(content) if isinstance(content, list) else str(content)
                ).strip()
                if val:
                    results.append(val)
        return results

    def _is_placeholder(self, s: str) -> bool:
        """检查字符串是否为占位符/模板变量"""
        if not s:
            return True
        if re.search(r"[{}]", s):
            return True
        if re.match(r"^#[a-zA-Z]", s):
            return True
        return not bool(re.search(r"[a-zA-Z\u4e00-\u9fff0-9]", s, re.UNICODE))

    def _first_valid(self, candidates: list[str]) -> str:
        """返回第一个非占位符的字符串"""
        for c in candidates:
            if c and not self._is_placeholder(c):
                return c
        return ""

    def _clean_author_string(self, s: str) -> str:
        """清理作者名称字符串"""
        s = re.sub(r"^by\s+", "", s, flags=re.I)
        s = re.sub(r"\(?\s*https?://\S+\s*\)?", "", s)
        s = re.sub(r",?\s+and\s+", ", ", s, flags=re.I)
        s = re.sub(r"\s*[-–—|]\s*$", "", s)
        return s.strip()

    # ==================== Schema.org 提取 ====================

    def _extract_schema_org(self) -> dict[str, Any] | None:
        """提取 Schema.org JSON-LD 数据（缓存）"""
        if self._schema_data is not None:
            return self._schema_data

        for script in self.soup.find_all("script", type="application/ld+json"):
            if script.string:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        self._schema_data = data
                        return data
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        self._schema_data = data[0]
                        return data[0]
                except (json.JSONDecodeError, TypeError):
                    continue
        self._schema_data = None
        return None

    def _get_schema_property(self, prop: str, default: str = "") -> str:
        """递归获取 Schema.org 中的属性，支持点号路径如 'author.name'"""
        data = self._extract_schema_org()
        if not data:
            return default

        def search(obj: Any, props: list[str]) -> str | None:
            if not props:
                return str(obj) if obj and not isinstance(obj, (dict, list)) else None
            if isinstance(obj, dict):
                if props[0] in obj:
                    return search(obj[props[0]], props[1:])
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        result = search(v, props)
                        if result:
                            return result
            elif isinstance(obj, list):
                for item in obj:
                    result = search(item, props)
                    if result:
                        return result
            return None

        result = search(data, prop.split("."))
        return result or default

    # ==================== 标题提取 ====================

    def _extract_title(self) -> str:
        """提取页面标题"""
        if value := self._select_value("title"):
            return value

        candidates = [
            self._get_meta_content(property="og:title"),
            self._get_meta_content(attrs={"name": "twitter:title"}),
            self._get_schema_property("headline"),
            self._get_schema_property("name"),
            self._get_meta_content(attrs={"name": "title"}),
        ]

        title_tag = self.soup.find("title")
        if title_tag and title_tag.string:
            candidates.append(title_tag.string.strip())

        h1 = self.soup.find("h1")
        if h1:
            candidates.append(h1.get_text(strip=True))

        return self._first_valid(candidates)

    # ==================== 作者提取 ====================

    def _extract_author(self) -> str:
        """提取作者名称"""
        if value := self._select_value("author"):
            return self._clean_author_string(value)

        author = self._first_valid(
            [
                self._get_meta_content(attrs={"name": "sailthru.author"}),
                self._get_meta_content(property="article:author"),
                self._get_meta_content(property="author"),
                self._get_meta_content(attrs={"name": "author"}),
                self._get_meta_content(attrs={"name": "byl"}),
                self._get_meta_content(attrs={"name": "authorList"}),
            ]
        )
        if author:
            return self._clean_author_string(author)

        authors = [
            a
            for a in self._get_meta_contents(attrs={"name": "citation_author"})
            if not self._is_placeholder(a)
        ]
        if not authors:
            authors = [
                a
                for a in self._get_meta_contents(property="dc.creator")
                if not self._is_placeholder(a)
            ]
        if authors:
            return ", ".join(authors)

        schema_author = self._get_schema_property("author.name")
        if schema_author:
            parts = [
                p.strip()
                for p in schema_author.split(",")
                if p.strip() and not self._is_placeholder(p)
            ]
            if parts:
                return ", ".join(parts[:10])

        rel_authors = self.soup.select('a[rel~="author"], address[rel~="author"]')
        if rel_authors and len(rel_authors) <= 3:
            names = []
            for el in rel_authors:
                text = el.get_text(strip=True)
                if (
                    text
                    and len(text) < 100
                    and text.lower() not in ("author", "authors")
                ):
                    names.append(text)
            if names:
                seen: set[str] = set()
                unique_names = [x for x in names if not (x in seen or seen.add(x))]
                return ", ".join(unique_names)

        for selector in [
            '[itemprop="author"]',
            ".author",
            '[href*="/author/"]',
            ".authors a",
        ]:
            matches = self.soup.select(selector)
            if matches and len(matches) <= 3:
                names = []
                for el in matches:
                    name = self._get_author_name(el)
                    if name:
                        names.append(name)
                if names:
                    seen = set()
                    unique_names = [x for x in names if not (x in seen or seen.add(x))]
                    return ", ".join(unique_names)

        h1 = self.soup.find("h1")
        if h1:
            sibling = getattr(h1, "next_sibling", None)
            for _ in range(3):
                if sibling and hasattr(sibling, "get_text"):
                    text = sibling.get_text(strip=True)
                    if byline := self._extract_byline(text):
                        return byline
                    if hasattr(sibling, "children"):
                        for child in sibling.children:
                            if hasattr(child, "get_text"):
                                text = child.get_text(strip=True)
                                if byline := self._extract_byline(text):
                                    return byline
                sibling = getattr(sibling, "next_sibling", None)
                if not sibling:
                    break

        return ""

    def _get_author_name(self, el: Tag) -> str:
        text = el.get_text(strip=True)
        if not text or len(text) > 100:
            return ""
        for child in el.find_all(recursive=False):
            child_text = child.get_text(strip=True)
            if 2 <= len(child_text) <= 50 and child_text != text:
                return child_text
        return text

    def _extract_byline(self, text: str) -> str | None:
        if not text or len(text) > 50:
            return None
        match = re.match(r"^By\s+([A-Z].+)$", text, re.I)
        if match:
            return match.group(1).strip()
        return None

    # ==================== 描述提取 ====================

    def _extract_description(self) -> str:
        """提取页面描述"""
        if value := self._select_value("description"):
            return value

        candidates = [
            self._get_meta_content(fuzzy=True, property="og:description"),
            self._get_meta_content(fuzzy=True, attrs={"name": "twitter:description"}),
            self._get_schema_property("description"),
            self._get_meta_content(fuzzy=True, attrs={"name": "description"}),
            self._get_meta_content(fuzzy=True, property="description"),
            self._get_meta_content(fuzzy=True, attrs={"name": "sailthru.description"}),
        ]
        return self._first_valid(candidates)

    # ==================== 发布日期提取 ====================

    def _extract_published(self) -> str:
        """提取发布日期"""
        published = ""

        if (
            (value := self._select_value("published"))
            or (value := self._get_schema_property("datePublished"))
            or (
                value := self._first_valid(
                    [
                        self._get_meta_content(attrs={"name": "publishDate"}),
                        self._get_meta_content(property="article:published_time"),
                        self._get_meta_content(attrs={"name": "sailthru.date"}),
                        self._get_meta_content(attrs={"name": "date"}),
                        self._get_meta_content(attrs={"name": "pubdate"}),
                    ]
                )
            )
        ):
            published = value
        else:
            abbr = self.soup.find("abbr", attrs={"itemprop": "datePublished"})
            if abbr and hasattr(abbr, "get") and (title := abbr.get("title", "")):
                published = str(title).strip()
            else:
                time_el = self.soup.find("time")
                if time_el:
                    published = (
                        time_el.get("datetime", "") if hasattr(time_el, "get") else ""
                    ) or time_el.get_text(strip=True)
                    published = str(published).strip()
                else:
                    h1 = self.soup.find("h1")
                    if h1:
                        sibling = getattr(h1, "next_sibling", None)
                        for _ in range(3):
                            if sibling and hasattr(sibling, "get_text"):
                                if parsed := self._parse_date_text(
                                    sibling.get_text(strip=True)
                                ):
                                    published = parsed
                                    break
                                if hasattr(sibling, "children"):
                                    for child in sibling.children:
                                        if hasattr(child, "get_text") and (
                                            parsed := self._parse_date_text(
                                                child.get_text(strip=True)
                                            )
                                        ):
                                            published = parsed
                                            break
                                    if published:
                                        break
                            sibling = getattr(sibling, "next_sibling", None)
                            if not sibling:
                                break

        return self._normalize_datetime(published)

    def _normalize_datetime(self, value: str) -> str:
        """将多种日期格式统一为 yyyy-mm-dd hh:mm:ss"""
        if not value:
            return ""

        value = re.sub(
            r"^(发表于|发布于|发布时间[：:]?\s*|Date[：:]?\s*)",
            "",
            value.strip(),
            flags=re.I,
        )
        normalized = (
            value.replace("年", "-")
            .replace("月", "-")
            .replace("日", " ")
            .replace("/", "-")
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()

        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(normalized, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

        match = re.search(
            r"(\d{4})-(\d{1,2})-(\d{1,2})"
            r"(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?",
            normalized,
        )
        if match:
            year, month, day = (
                match.group(1),
                match.group(2).zfill(2),
                match.group(3).zfill(2),
            )
            hour = match.group(4).zfill(2) if match.group(4) else "00"
            minute = match.group(5).zfill(2) if match.group(5) else "00"
            second = match.group(6).zfill(2) if match.group(6) else "00"
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"

        return value

    def _parse_date_text(self, text: str) -> str:
        """解析日期文本，支持英文和中文格式"""
        if not text:
            return ""

        match = re.search(
            r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})[日]?\s*"
            r"(?:\s+(\d{1,2}):(\d{1,2})(?::(\d{1,2}))?)?",
            text,
        )
        if match:
            year = match.group(1)
            month = match.group(2).zfill(2)
            day = match.group(3).zfill(2)
            hour = match.group(4).zfill(2) if match.group(4) else "00"
            minute = match.group(5).zfill(2) if match.group(5) else "00"
            second = match.group(6).zfill(2) if match.group(6) else "00"
            return f"{year}-{month}-{day} {hour}:{minute}:{second}"

        match = re.search(
            r"\b(\d{1,2})\s+(January|February|March|April|May|June|"
            r"July|August|September|October|November|December)\s+(\d{4})\b",
            text,
            re.I,
        )
        if match:
            day = match.group(1).zfill(2)
            month = self.MONTH_MAP[match.group(2).lower()]
            return f"{match.group(3)}-{month}-{day} 00:00:00"

        match = re.search(
            r"\b(January|February|March|April|May|June|"
            r"July|August|September|October|November|December)\s+"
            r"(\d{1,2}),?\s+(\d{4})\b",
            text,
            re.I,
        )
        if match:
            month = self.MONTH_MAP[match.group(1).lower()]
            day = match.group(2).zfill(2)
            return f"{match.group(3)}-{month}-{day} 00:00:00"

        return ""

    # ==================== 站点名称提取 ====================

    def _extract_site(self) -> str:
        """提取站点名称"""
        if value := self._select_value("site"):
            return value

        candidates = [
            self._get_schema_property("publisher.name"),
            self._get_meta_content(property="og:site_name"),
            self._get_schema_property("WebSite.name"),
            self._get_schema_property("sourceOrganization.name"),
            self._get_schema_property("copyrightHolder.name"),
            self._get_schema_property("isPartOf.name"),
            self._get_meta_content(attrs={"name": "application-name"}),
            self._get_meta_content(attrs={"name": "copyright"}),
            self._get_meta_content(attrs={"name": "twitter:site"}),
        ]

        for candidate in candidates:
            if candidate and len(candidate.split()) <= 6:
                return candidate

        if self.url:
            parsed = urlparse(self.url)
            return parsed.netloc

        return ""

    # ==================== 图片提取 ====================

    def _extract_image(self) -> str:
        """提取主图片 URL"""
        for attr in ("src", "href", "content", "data-src"):
            if value := self._select_value("image", attr=attr, resolve_url=True):
                return value

        candidates = [
            self._get_meta_content(property="og:image"),
            self._get_meta_content(attrs={"name": "twitter:image"}),
            self._get_schema_property("image.url"),
            self._get_schema_property("image"),
            self._get_meta_content(attrs={"name": "sailthru.image.full"}),
        ]

        for candidate in candidates:
            if candidate:
                return self._resolve_url(candidate)

        img = self.soup.find("img")
        if img and hasattr(img, "get"):
            src = img.get("src")
            if src:
                return self._resolve_url(str(src))

        return ""

    # ==================== 图标提取 ====================

    def _extract_favicon(self) -> str:
        """提取网站图标"""
        for attr in ("href", "src", "content"):
            if value := self._select_value("favicon", attr=attr, resolve_url=True):
                return value

        for rel in ["icon", "shortcut icon", "apple-touch-icon"]:
            link = self.soup.find("link", rel=rel)
            if link and hasattr(link, "get"):
                href = link.get("href")
                if href:
                    return self._resolve_url(str(href))

        if self.url:
            return urljoin(self.url, "/favicon.ico")

        return ""

    # ==================== 语言提取 ====================

    def _extract_language(self) -> str:
        """提取页面语言"""
        if value := self._select_value("language"):
            return value.replace("_", "-")

        html_tag = self.soup.find("html")
        if html_tag and hasattr(html_tag, "get"):
            lang_attr = html_tag.get("lang")
            if lang_attr:
                return str(lang_attr).replace("_", "-")

        lang = self._first_valid(
            [
                self._get_meta_content(attrs={"http-equiv": "Content-Language"}),
                self._get_meta_content(property="og:locale"),
                self._get_meta_content(attrs={"name": "content-language"}),
            ]
        )
        if lang:
            return lang.replace("_", "-")

        schema_lang = self._get_schema_property("inLanguage")
        if schema_lang:
            return schema_lang.replace("_", "-")

        return ""

    # ==================== Domain / URL 提取 ====================

    def _extract_domain(self) -> str:
        """从 URL 或 canonical 链接提取域名"""
        if self.url:
            try:
                parsed = urlparse(self.url)
                return parsed.hostname.replace("www.", "") if parsed.hostname else ""
            except Exception as e:
                logger.debug("URL domain parse error: %s", e)

        canonical = self.soup.find("link", rel="canonical")
        if canonical and hasattr(canonical, "get"):
            href = str(canonical.get("href", ""))
            if href:
                try:
                    parsed = urlparse(href)
                    return (
                        parsed.hostname.replace("www.", "") if parsed.hostname else ""
                    )
                except Exception as e:
                    logger.debug("Canonical domain parse error: %s", e)

        return ""

    def _extract_url(self) -> str:
        """提取或回退原始 URL"""
        if self.url:
            return self.url
        candidates = [
            self._get_meta_content(property="og:url"),
            self._get_meta_content(attrs={"name": "twitter:url"}),
            self._get_schema_property("url"),
        ]
        canonical = self.soup.find("link", rel="canonical")
        if canonical and hasattr(canonical, "get"):
            href = canonical.get("href", "")
            if isinstance(href, str) and href.strip():
                candidates.append(href.strip())
        self.url = self._first_valid(candidates)
        return self.url

    # ==================== 字数统计 ====================

    def _extract_word_count(self) -> int:
        """统计正文字数（中文字符 + 英文单词）"""
        content = self._extract_content(format="text")
        if not content:
            return 0

        text = re.sub(r"\s+", " ", content.strip())
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        return chinese_chars + english_words

    # ==================== Meta 标签提取 ====================

    def _extract_meta_tags_list(self) -> list[dict[str, str]]:
        """提取所有 meta 标签为列表格式"""
        if self._meta_tags_list is not None:
            return self._meta_tags_list

        self._meta_tags_list = []
        for meta in self.soup.find_all("meta"):
            tag_data: dict[str, str] = {}
            for key in ("name", "property", "http-equiv", "content"):
                if val := meta.get(key):
                    tag_data[key] = " ".join(val) if isinstance(val, list) else str(val)
            if tag_data:
                self._meta_tags_list.append(tag_data)

        return self._meta_tags_list

    def _extract_meta_tags(self) -> dict[str, str]:
        """提取所有 meta 标签为字典格式"""
        meta_dict: dict[str, str] = {}
        for meta in self.soup.find_all("meta"):
            key = meta.get("name") or meta.get("property") or meta.get("http-equiv")
            value = meta.get("content")
            if key and value:
                k_str = " ".join(key) if isinstance(key, list) else str(key)
                v_str = " ".join(value) if isinstance(value, list) else str(value)
                meta_dict[k_str.strip()] = v_str.strip()
        return meta_dict

    # ==================== 正文内容提取 ====================

    def _extract_content(self, format: str = "text") -> str:
        """提取正文内容

        优先级：自定义 selector → article → main → div.content → body
        """
        content_el = None

        custom_selector = self.selectors.get("content")
        if custom_selector:
            content_el = self.soup.select_one(custom_selector)

        if content_el is None:
            for sel in (
                "article",
                "main",
                "div.content",
                "div.post",
                "div.article",
                "div.entry",
                "div.post-content",
                "div.article-content",
                "#content",
            ):
                content_el = self.soup.select_one(sel)
                if content_el:
                    break

        if content_el is None:
            content_el = self.soup.find("body")

        if content_el is None:
            return ""

        el = copy.copy(content_el)
        for tag in el.find_all(
            [
                "script",
                "style",
                "nav",
                "header",
                "footer",
                "aside",
                "form",
                "iframe",
                "noscript",
            ]
        ):
            tag.decompose()

        if format == "html":
            return str(el)
        elif format == "markdown":
            converter = MarkdownConverter()
            res = converter.convert(str(el), base_url=self.url)
            if res:
                return res
            return el.get_text(separator="\n", strip=True)

        return el.get_text(separator=" ", strip=True)

    # ==================== Markdown 生成 ====================

    def to_markdown(self, tags: list[str] | None = None) -> str:
        """将 HTML 转换为带 Frontmatter 的 Markdown 格式字符串"""
        title = self._extract_title()
        source = self.url
        author = self._extract_author()
        published = self._extract_published()
        description = self._extract_description()
        image = self._extract_image()

        markdown_body = self._extract_content(format="markdown")

        tags_list: list[str] = []
        if tags is not None:
            tags_list = list(tags)
        else:
            tags_selector = self.selectors.get("tags")
            if tags_selector:
                el_list = self.soup.select(tags_selector)
                for el in el_list:
                    val = el.get_text(strip=True)
                    if val and val not in tags_list:
                        tags_list.append(val)

            if not tags_list:
                keywords = self._first_valid(
                    [
                        self._get_meta_content(name="keywords"),
                        self._get_meta_content(property="article:tag"),
                    ]
                )
                if keywords:
                    for kw in re.split(r"[,，;；]", keywords):
                        kw_clean = kw.strip()
                        if kw_clean and kw_clean not in tags_list:
                            tags_list.append(kw_clean)

            if not tags_list:
                tags_list = ["clippings"]

        lines = ["---"]
        if title:
            lines.append(f'title: "{title}"')
        if source:
            lines.append(f'source: "{source}"')
        if author:
            lines.append("author:")
            lines.append(f'  - "[[{author}]]"')
        if published:
            lines.append(f"published: {published}")
        created_date = datetime.now().strftime("%Y-%m-%d")
        lines.append(f"created: {created_date}")
        if description:
            lines.append(f'description: "{description}"')
        if tags_list:
            lines.append("tags:")
            for t in tags_list:
                lines.append(f'  - "{t}"')
        lines.append("---")

        parts = []
        if image:
            parts.append(f"![Image]({image})")
        if description:
            parts.append(f"> {description}")
        if markdown_body:
            parts.append(markdown_body)

        return "\n".join(lines) + "\n\n" + "\n\n".join(parts) + "\n"

    # ==================== ORM 转换 ====================

    def to_content_model(
        self,
        platform: str | None = None,
        data_type: str | None = "4",
        content_id: str | None = None,
        user_id: str | None = None,
    ) -> Any:
        """将提取的元数据转换为 Content ORM 模型实例"""
        try:
            from ..models.content import Content
        except (ImportError, ValueError):
            from models.content import Content

        metadata = self.extract()

        try:
            content_val = self._extract_content(format="markdown")
        except Exception:
            content_val = metadata.content

        return Content.from_metadata(
            metadata=metadata,
            url=self.url,
            platform=platform,
            data_type=data_type,
            content_id=content_id,
            user_id=user_id,
            content_val=content_val,
        )


_WebExtractor = WebExtractor


# ==================== 便捷函数 ====================


def extract_metadata(
    html: str,
    url: str = "",
    selectors: dict[str, str] | None = None,
    content_format: str = "text",
) -> Metadata:
    """从 HTML 字符串提取网页元数据。

    Args:
        html: 要解析的 HTML 字符串内容。
        url: 网页的原始 URL（选填，用于解析相对路径的图片、favicon 等）。
        selectors: 自定义 CSS 选择器映射（选填，用于提取特定字段）。
        content_format: 返回的内容提取格式，支持 "text", "html", "markdown"（选填，默认 "text"）。

    Returns:
        Metadata: 提取出的网页元数据对象。
    """
    extractor = WebExtractor(
        html, url, selectors=selectors, content_format=content_format
    )
    return extractor.extract()


def extract_metadata_from_url(
    url: str,
    timeout: int = 10,
    selectors: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    content_format: str = "text",
) -> Metadata:
    """从指定的网页 URL 获取并提取网页元数据。

    Args:
        url: 目标网页的 HTTP/HTTPS 链接。
        timeout: 网络请求超时时间（单位：秒，默认 10）。
        selectors: 自定义 CSS 选择器映射（选填，用于提取特定字段）。
        headers: 自定义 HTTP 请求头（选填）。
        content_format: 返回的内容提取格式，支持 "text", "html", "markdown"（选填，默认 "text"）。

    Returns:
        Metadata: 提取出的网页元数据对象。

    Raises:
        requests.exceptions.RequestException: 当网络连接错误、超时或 HTTP 状态码为 4xx/5xx 时抛出。
    """
    import requests

    req_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    if headers:
        req_headers.update(headers)

    response = requests.get(url, timeout=timeout, headers=req_headers)
    response.raise_for_status()

    # 修复 requests 对没有声明编码的中文网页可能识别为 ISO-8859-1 的乱码问题
    if response.encoding == "ISO-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"

    extractor = WebExtractor(
        response.text, url, selectors=selectors, content_format=content_format
    )
    return extractor.extract()


def generate_markdown(
    html: str,
    url: str = "",
    selectors: dict[str, str] | None = None,
    tags: list[str] | None = None,
) -> str:
    """从 HTML 字符串提取核心内容并转换为 Markdown 格式。

    Args:
        html: 要解析的 HTML 字符串内容。
        url: 网页的原始 URL（选填，用于链接重定向等）。
        selectors: 自定义 CSS 选择器映射（选填）。
        tags: 转换为 Markdown 时保留的 HTML 标签列表（选填）。

    Returns:
        str: 转换后的 Markdown 字符串。若转换失败，则返回空字符串。
    """
    extractor = WebExtractor(html, url, selectors=selectors)
    return extractor.to_markdown(tags=tags)
