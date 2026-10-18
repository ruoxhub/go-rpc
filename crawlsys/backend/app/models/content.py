from sqlalchemy import String, Integer, Text, DateTime, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, List, Any
from datetime import datetime
from pydantic import Field

from .base import Base, GeneralBase, BaseSchema, TimeMixin, IDMixin

# ============== SQLAlchemy ORM 模型 ==============

class Content(GeneralBase, Base):
    """内容模型 - 融合文章/视频/帖子数据 - 使用 SQLAlchemy 2.0 现代语法"""

    # ---- 自动注册元信息 ----
    datatype_key = "content"
    unique_field = "content_id"
    update_fields = [
        "content_id", "platform", "title", "content", "description",
        "author", "user_id", "pic", "thumbnail", "url", "duration",
        "pub_time", "view_count", "comment_count", "like_count",
        "share_count", "favorites", "extend", "is_detail"
    ]

    __tablename__ = "t_busi_content"

    # 内容标识字段
    content_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="平台内容 ID")
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, comment="平台用户 ID")

    # 作者信息
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='作者')

    # 内容字段
    pic: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="封面")
    thumbnail: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment='视频封面')
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, comment="标题")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="内容")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="简介")
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True, comment="链接")

    # 时间字段
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment='时长')
    pub_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='发布时间')
    download_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='下载时间')
    dispose_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment='处理时间')
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='位置')

    # 统计字段
    share_count: Mapped[int] = mapped_column(Integer, default=0, comment='分享数')
    repost_count: Mapped[int] = mapped_column(Integer, default=0, comment='转发数')
    comment_count: Mapped[int] = mapped_column(Integer, default=0, comment='评论数')
    like_count: Mapped[int] = mapped_column(Integer, default=0, comment='爱心数')
    view_count: Mapped[int] = mapped_column(Integer, default=0, comment='播放数')
    favorites: Mapped[Optional[int]] = mapped_column(Integer, default=0, comment="收藏数")

    # 分类字段
    category_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment='分类 ID')
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment='数据源 ID')
    source: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment='数据源名称')
    platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="所属平台")

    # 类型字段
    data_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, comment='数据类型 1:新闻 2:社交 3:视频 4:文章')

    # 扩展字段
    extend: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="扩展字段 (JSON 字符串)")

    # 调度追踪字段
    is_detail: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="是否已抓详情")
    subtitle_fetched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="是否已抓字幕")
    comment_fetched: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="是否已抓评论")
    is_download: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", comment="媒体是否已下载")
    __table_args__ = (
        Index('idx_base_content_content_id', 'content_id'),
        Index('idx_base_content_user_id', 'user_id'),
        Index('idx_base_content_platform', 'platform'),
        Index('idx_base_content_pub_time', 'pub_time'),
        Index('uq_base_content_platform_content_id', 'platform', 'content_id', unique=True),
        {'schema': 'public'}
    )

    @classmethod
    def from_metadata(
        cls,
        metadata: Any,
        url: Optional[str] = None,
        platform: Optional[str] = None,
        data_type: Optional[str] = "4",
        content_id: Optional[str] = None,
        user_id: Optional[str] = None,
        content_val: Optional[str] = None,
    ) -> "Content":
        """从网页元数据构造 Content 实例"""
        import hashlib
        import json
        from datetime import datetime

        # 1. 自动生成 content_id，如果未指定且 url 存在
        final_url = url or getattr(metadata, "url", None) or getattr(metadata, "source", "")
        if not content_id and final_url:
            content_id = hashlib.md5(final_url.encode("utf-8")).hexdigest()

        # 2. 解析发布时间
        pub_time = None
        published_str = getattr(metadata, "published", "")
        if published_str:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    pub_time = datetime.strptime(published_str, fmt)
                    break
                except ValueError:
                    continue

        # 3. 设置所属平台与数据源
        domain = getattr(metadata, "domain", "")
        site = getattr(metadata, "site", "")
        final_platform = platform or domain or site or "web"
        final_source = site or domain or final_platform

        # 4. 组装扩展字段 (JSON 字符串)
        extend_data = {
            "favicon": getattr(metadata, "favicon", ""),
            "language": getattr(metadata, "language", ""),
            "domain": domain,
            "word_count": getattr(metadata, "word_count", 0),
            "schema_org_data": getattr(metadata, "schema_org_data", None),
            "meta_tags": getattr(metadata, "meta_tags", []),
        }

        # 5. 构造 Content 实例
        # md5().hexdigest() 固定 32 字符；author/pic/thumbnail/title/url/source/platform/data_type
        # 都已由各自列长度约束（max_length 在 Pydantic 层校验，DB 层超长会报错），无需手动切片
        return cls(
            datatype="content",
            content_id=content_id,
            user_id=user_id,
            author=getattr(metadata, "author", None) or None,
            pic=getattr(metadata, "image", None) or None,
            thumbnail=getattr(metadata, "image", None) or None,
            title=getattr(metadata, "title", None) or None,
            content=content_val or getattr(metadata, "content", ""),
            description=getattr(metadata, "description", ""),
            url=final_url or None,
            pub_time=pub_time,
            download_time=datetime.now(),
            dispose_time=datetime.now(),
            platform=final_platform or None,
            source=final_source or None,
            data_type=data_type,
            extend=json.dumps(extend_data, ensure_ascii=False),
        )

# 别名映射，保证向前兼容
BusContent = Content
BaseContent = Content




# ============== Pydantic DTO 定义 ==============

class ContentBase(BaseSchema):
    """内容基础 Schema"""
    content_id: Optional[str] = Field(None, max_length=64, description="平台内容 ID")
    user_id: Optional[str] = Field(None, max_length=64, description="平台用户 ID")
    author: Optional[str] = Field(None, max_length=255, description="作者")
    pic: Optional[str] = Field(None, max_length=512, description="封面")
    thumbnail: Optional[str] = Field(None, max_length=512, description="视频封面")
    title: Optional[str] = Field(None, max_length=512, description="标题")
    content: Optional[str] = Field(None, description="内容")
    description: Optional[str] = Field(None, description="简介")
    url: Optional[str] = Field(None, max_length=1024, description="链接")
    duration: Optional[int] = Field(None, description="时长 (秒)")
    pub_time: Optional[datetime] = Field(None, description="发布时间")
    location: Optional[str] = Field(None, max_length=255, description="位置")
    share_count: int = Field(default=0, description="分享数")
    repost_count: int = Field(default=0, description="转发数")
    comment_count: int = Field(default=0, description="评论数")
    like_count: int = Field(default=0, description="爱心数")
    view_count: int = Field(default=0, description="播放数")
    favorites: int = Field(default=0, description="收藏数")
    category_id: Optional[int] = Field(None, description="分类 ID")
    source_id: Optional[int] = Field(None, description="数据源 ID")
    source: Optional[str] = Field(None, max_length=255, description="数据源名称")
    data_type: Optional[str] = Field(None, max_length=10, description="数据类型")
    platform: Optional[str] = Field(None, max_length=50, description="所属平台")


class ContentCreate(ContentBase):
    """创建内容请求"""
    pass


class ContentUpdate(BaseSchema):
    """更新内容请求"""
    title: Optional[str] = None
    content: Optional[str] = None
    description: Optional[str] = None
    pub_time: Optional[datetime] = None
    like_count: Optional[int] = None
    view_count: Optional[int] = None
    comment_count: Optional[int] = None


class ContentResponse(ContentBase, IDMixin, TimeMixin):
    """内容响应"""
    download_time: Optional[datetime] = None
    dispose_time: Optional[datetime] = None
    extend: Optional[str] = None


class ContentListResponse(BaseSchema):
    """内容列表响应"""
    total: int
    items: List[ContentResponse]
