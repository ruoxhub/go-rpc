"""Parser DTO layer — 继承 models/ 中的 Pydantic Schema 复用字段定义。

设计原则：
- 字段定义不在本文件重复声明：UserDTO 继承 UserBase，PostDTO/VideoDTO/ContentDTO
  继承 ContentBase，CommentDTO 继承 CommentSchema，MediaDTO 继承 MediaSchema，
  JobDTO 继承 JobBase。新增字段或覆盖父类校验严格度，是 parser DTO 唯一职责。
- 所有 DTO 多继承 BaseDTO + 对应 models Schema：
  * BaseDTO 是真正的 BaseModel 子类，承载 parser 共享配置（extra=ignore + frozen）
    和 to_dict() 兼容方法。
  * ParsedItem.data 类型为具体的 BaseDTO，避免 pydantic v2 对抽象 BaseModel
    字段做严格 model_type 校验时拒绝多继承子类。
- 解放放宽：avatar/pub_time/publish_time/created_at/extend 用 Any 覆盖父类的
  max_length / Optional[datetime] 校验——这些字段在各平台间传值类型漂移
  （list / datetime / json string / None 等）。
- gender / type 覆盖为 int：父类用 IntEnum，parser 直接 yield 0/1/2，避免 enum coerce 异常。
"""

from typing import Any, ClassVar, List, Literal

from pydantic import BaseModel, ConfigDict, Field

from models import (
    CommentSchema,
    ContentBase,
    JobBase,
    MediaSchema,
    UserBase,
)
from models.follow import FollowBase
from models.tiktok import TkChallengeBase

ItemKind = Literal["user", "post", "video", "media", "comment", "job", "content", "challenge", "follow"]


class BaseDTO(BaseModel):
    """Parser DTO 共同基类 — 提供宽容输入 + 不可变 + to_dict 兼容方法。

    所有 7 个 parser DTO 都通过 `class XxxDTO(BaseDTO, <ModelsSchema>)` 多继承拿到
    本类的配置；在 MRO 中 BaseDTO 位于左侧，model_config 按 MRO 合并后由本类决定
    最终的 frozen/extra 行为。
    """

    model_config = ConfigDict(
        extra="ignore",
        frozen=True,
        populate_by_name=True,
        use_enum_values=True,
        from_attributes=True,
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class UserDTO(BaseDTO, UserBase):
    """用户 DTO — 继承 UserBase，覆盖 avatar/gender 严格度。"""
    # 覆盖：xhs 等平台 avatar 字段会传 list[str]；UserBase 上是 max_length=255 的 str
    avatar: Any = ""
    # 覆盖：parser 直接 yield int 0/1/2；UserBase 上是 Optional[GenderEnum]
    gender: int | None = 0
    # parser 独有
    url: str | None = ""
    created_at: Any = ""
    extend: Any = ""


class PostDTO(BaseDTO, ContentBase):
    """帖子 DTO — 复用 ContentBase 的 20+ 字段，仅追加 parser wire 格式专属字段。"""
    pub_time: Any = ""
    # parser wire 格式：旧调用方 yield 'post_id'；与 ContentBase.content_id 并存
    post_id: str | None = ""
    author: str | None = ""
    extend: Any = ""


class VideoDTO(BaseDTO, ContentBase):
    """视频 DTO — 与 PostDTO 同构，但 wire 格式字段是 video_id。"""
    pub_time: Any = ""
    video_id: str | None = ""
    duration: int | None = 0
    author: str | None = ""
    extend: Any = ""


class CommentDTO(BaseDTO, CommentSchema):
    """评论 DTO — CommentSchema 已含 12 字段，仅追加 parser 独有 location/user_url 等。"""
    pub_time: Any = ""
    relation_id: str | None = ""
    user_url: str | None = ""
    location: str | None = ""
    extend: Any = ""


class MediaDTO(BaseDTO, MediaSchema):
    """媒体 DTO — 覆盖 MediaSchema.type 为 int（parser 直接 yield 1/2 数字）。"""
    # 覆盖：MediaSchema 上是 Optional[MediaTypeEnum]
    type: int | None = 0
    pub_time: Any = ""
    # parser 独有 wire 格式字段
    relation_id: str | None = ""
    post_id: str | None = ""
    video_id: str | None = ""
    source_url: str | None = ""
    extend: Any = ""


class JobDTO(BaseDTO, JobBase):
    """职位 DTO — JobBase 覆盖 33 字段中的 32 个，仅追加 publish_time/raw_data。"""
    publish_time: Any = ""
    raw_data: dict = Field(default_factory=dict)
    extend: Any = ""


class ContentDTO(BaseDTO, ContentBase):
    """通用 web content DTO — 全部字段直接来自 ContentBase。"""
    pub_time: Any = ""
    domain: str | None = ""
    extend: Any = ""


class ChallengeDTO(BaseDTO, TkChallengeBase):
    """TikTok challenge DTO — 复用 TkChallengeBase 字段定义。"""


class FollowDTO(BaseDTO, FollowBase):
    """用户关系 DTO — 复用 FollowBase 字段定义，追加 parser wire 格式专属字段。"""

    extend: Any = ""


class ParsedItem(BaseModel):
    """Parser 出口的统一封装 — kind 标签 + 强类型 DTO 数据载荷。"""

    model_config = ConfigDict(frozen=True)

    kind: ItemKind
    data: BaseDTO  # 具体 BaseDTO 而非抽象 BaseModel — 避免 pydantic 严格 model_type 校验

    _DTO_BY_KIND: ClassVar[dict[str, type[BaseDTO]]] = {}

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "ParsedItem":
        if not cls._DTO_BY_KIND:
            raise RuntimeError("DTO registry not initialized — import dto module first")
        kind = item.get("datatype")
        if kind is None:
            raise ValueError(f"Item dict missing 'datatype' key: {item!r}")
        dto_cls = cls._DTO_BY_KIND.get(kind)
        if dto_cls is None:
            raise ValueError(f"Unknown item kind: {kind}")
        # extra="ignore" 自动丢弃 datatype 等未声明字段
        return cls(kind=kind, data=dto_cls(**item))


ParsedItem._DTO_BY_KIND = {
    "user": UserDTO,
    "post": PostDTO,
    "video": VideoDTO,
    "comment": CommentDTO,
    "media": MediaDTO,
    "job": JobDTO,
    "content": ContentDTO,
    "challenge": ChallengeDTO,
    "follow": FollowDTO,
}
