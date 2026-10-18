from sqlalchemy import String, Integer, Float, Text, DateTime, Index, select, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from pydantic import Field

from .base import Base, BaseSchema, IDMixin
from common.logging import get_logger

logger = get_logger(__file__)


if TYPE_CHECKING:
    from core.config import PlatformQuota
    from storage import SQLAlchemyDB

# ============== 状态枚举 ==============

class PlatformStatus:
    """站点状态枚举（bs_status，String(1)）。

    - ENABLED  = "1"  启用（默认值，新建站点初始状态）
    - DISABLED = "0"  禁用
    - DELETED  = "D"  软删除（列表默认过滤）
    """

    ENABLED = "1"
    DISABLED = "0"
    DELETED = "D"

    DEFAULT = "1"
    ALL = {ENABLED, DISABLED, DELETED}

    @classmethod
    def is_valid(cls, value: Optional[str]) -> bool:
        return value in cls.ALL


# ============== SQLAlchemy ORM 模型 ==============

class platformSource(Base):
    """站点来源模型 - 对应 t_busi_platform_source 表"""
    __tablename__ = "t_busi_platform"
    __table_args__ = (
        Index('idx_platform_source_status', 'bs_status'),
        Index('idx_platform_source_language', 'bs_language_code'),
        {'schema': 'public'}
    )

    bs_id: Mapped[int] = mapped_column("bs_id", Integer, primary_key=True, autoincrement=True, comment='站点 id')
    bs_name: Mapped[Optional[str]] = mapped_column("bs_name", String(100), nullable=True, comment='站点名称')
    bs_industryid: Mapped[Optional[int]] = mapped_column("bs_industryid", Integer, nullable=True, comment='行业分类 id')
    bs_mediaid: Mapped[Optional[int]] = mapped_column("bs_mediaid", Integer, nullable=True, comment='媒体类型 id')
    bs_countryid: Mapped[Optional[int]] = mapped_column("bs_countryid", Integer, nullable=True, comment='国家 id')
    bs_languageid: Mapped[Optional[int]] = mapped_column("bs_languageid", Integer, nullable=True, comment='语种 id')
    bs_url: Mapped[Optional[str]] = mapped_column("bs_url", String(2048), nullable=True, comment='url')
    bs_status: Mapped[Optional[str]] = mapped_column(
        "bs_status",
        String(1),
        nullable=True,
        default=PlatformStatus.ENABLED,
        comment="状态（1=启用, 0=禁用, D=软删除）",
    )
    bs_weight: Mapped[Optional[int]] = mapped_column("bs_weigth", Integer, nullable=True, comment='权重')
    bs_modifystatus: Mapped[Optional[str]] = mapped_column("bs_modifystatus", String(1), nullable=True, comment='可修改状态')
    bs_remark: Mapped[Optional[str]] = mapped_column("bs_remark", Text, nullable=True, comment='备注')
    bs_errtype: Mapped[Optional[int]] = mapped_column("bs_errtype", Integer, nullable=True, comment='站点错误描述')
    bs_isproxy: Mapped[Optional[int]] = mapped_column("bs_isproxy", Integer, nullable=True, comment='是否需要代理  1：需要  2：不需要')
    bs_down_type: Mapped[int] = mapped_column("bs_down_type", Integer, default=1, comment='下载类型')
    bs_instock: Mapped[str] = mapped_column("bs_instock", String(1), default='0', comment='是否入库')
    dept: Mapped[Optional[str]] = mapped_column("dept", String(255), nullable=True, comment='部门')
    bs_crawler_comment: Mapped[Optional[str]] = mapped_column("bs_cralwer_commnet", String(1), nullable=True, comment='采集评论（1:是，0:否）')
    bs_crawler_level: Mapped[Optional[str]] = mapped_column("bs_cralwer_level", String(1), nullable=True, comment='层级（1:一级，2:二级，3:三级）')
    bs_keywords: Mapped[Optional[str]] = mapped_column("bs_keywords", Text, nullable=True, comment='关键词')
    create_by: Mapped[Optional[str]] = mapped_column("create_by", String(100), nullable=True, comment='创建人')
    create_time: Mapped[Optional[datetime]] = mapped_column("create_time", DateTime, nullable=True, comment='创建时间')
    is_downall: Mapped[int] = mapped_column("is_downall", Integer, default=0, comment='下载策略：0:不下载，1:下载所有，2:仅图片附件')
    bs_browser_type: Mapped[int] = mapped_column("bs_browser_type", Integer, default=1, comment='浏览器类型（1：chrome; 2：firefox）')
    bs_web_id: Mapped[Optional[int]] = mapped_column("bs_web_id", Integer, nullable=True, comment='t_busi_web id')
    bs_language_code: Mapped[Optional[str]] = mapped_column("bs_language_code", String(10), nullable=True, comment='语种代码')
    bs_max_reach_page: Mapped[Optional[int]] = mapped_column("bs_max_reach_page", Integer, nullable=True, comment='最大实际翻页数')
    bs_last_all_item_time: Mapped[Optional[datetime]] = mapped_column("bs_last_all_item_time", DateTime, nullable=True, comment='最新采集到列表的时间')
    bs_last_un_item_time: Mapped[Optional[datetime]] = mapped_column("bs_last_un_item_time", DateTime, nullable=True, comment='最新采集到列表的时间')
    bs_resource_type: Mapped[Optional[str]] = mapped_column("bs_reaource_type", String(500), nullable=True, comment='资源类型，字典类型 resourceTypeDict（多个以，隔开）')
    bs_display_type: Mapped[Optional[str]] = mapped_column("bs_display_type", String(100), nullable=True, comment='采集数据显示类型')
    bs_platform_code: Mapped[Optional[str]] = mapped_column("bs_platform_code", String(100), nullable=True, unique=True, comment='网站代码')
    bs_ico_url: Mapped[Optional[str]] = mapped_column("bs_ico_url", String(512), nullable=True, comment='网站图标 URL')
    bs_desc: Mapped[Optional[str]] = mapped_column("bs_desc", Text, nullable=True, comment='网站介绍')

    # 限流配额配置
    bs_concurrency: Mapped[Optional[int]] = mapped_column("bs_concurrency", Integer, nullable=True, default=1, comment='并发数')
    bs_rps: Mapped[Optional[float]] = mapped_column("bs_rps", Float, nullable=True, default=1.0, comment='每秒请求数')
    bs_burst: Mapped[Optional[int]] = mapped_column("bs_burst", Integer, nullable=True, default=3, comment='令牌桶突发量')
    bs_cooldown: Mapped[Optional[int]] = mapped_column("bs_cooldown", Integer, nullable=True, default=300, comment='被限流后冷却秒数')

    def to_quota(self) -> "PlatformQuota":
        """把 ORM 行转换为 PlatformQuota 值对象；以 bs_platform_code 为平台键。"""
        from core.config import PlatformQuota

        if not self.bs_platform_code:
            raise ValueError(f"platformSource bs_id={self.bs_id} missing bs_platform_code")
        return PlatformQuota(
            platform=self.bs_platform_code,
            concurrency=int(self.bs_concurrency or 1),
            rps=float(self.bs_rps or 1.0),
            burst=int(self.bs_burst or 3),
            cooldown_on_block=int(self.bs_cooldown or 300),
        )

    @classmethod
    async def load_active_quotas(cls, db: "SQLAlchemyDB") -> list["PlatformQuota"]:
        """拉取 bs_status='1' 且 bs_platform_code 非空的全部启用平台配额。"""
        async with db.asession_scope() as session:
            result = await session.execute(
                select(cls).where(
                    cls.bs_status == PlatformStatus.ENABLED,
                    cls.bs_platform_code.isnot(None),
                    func.trim(cls.bs_platform_code) != "",
                )
            )
            rows = result.scalars().all()
        
        quotas: list["PlatformQuota"] = []
        for row in rows:
            try:
                quotas.append(row.to_quota())
            except Exception as e:
                logger.warning("Skipping invalid platform row bs_id=%s: %s", getattr(row, "bs_id", None), e)
        return quotas


    @classmethod
    async def load_quota_by_code(cls, db: "SQLAlchemyDB", code: str) -> Optional["PlatformQuota"]:
        """按 bs_platform_code 精确加载单个平台配额；不存在返回 None。"""
        async with db.asession_scope() as session:
            result = await session.execute(
                select(cls).where(cls.bs_platform_code == code)
            )
            row = result.scalars().first()
        return row.to_quota() if row else None





# ============== Pydantic DTO 定义 ==============

class platformSourceBase(BaseSchema):
    """站点来源基础 Schema"""
    bs_platformname: Optional[str] = Field(None, max_length=100, description="站点名称")
    bs_industryid: Optional[int] = Field(None, description="行业分类 ID")
    bs_mediaid: Optional[int] = Field(None, description="媒体类型 ID")
    bs_countryid: Optional[int] = Field(None, description="国家 ID")
    bs_languageid: Optional[int] = Field(None, description="语种 ID")
    bs_url: Optional[str] = Field(None, max_length=2048, description="URL")
    bs_status: Optional[str] = Field(
        PlatformStatus.DEFAULT,
        max_length=1,
        description="状态（1=启用, 0=禁用, D=软删除）",
    )
    bs_keywords: Optional[str] = Field(None, description="关键词")
    bs_language_code: Optional[str] = Field(None, max_length=10, description="语种代码")


class platformSourceCreate(platformSourceBase):
    """创建站点来源请求"""
    pass


class platformSourceResponse(platformSourceBase, IDMixin):
    """站点来源响应"""
    create_time: Optional[datetime] = None
    bs_desc: Optional[str] = None
