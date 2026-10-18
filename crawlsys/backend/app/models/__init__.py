"""数据模型 - SQLAlchemy ORM + Pydantic Schemas"""

# ==================== SQLAlchemy ORM 物理模型 ====================
from .base import Base, GeneralBase
from .user import User, BusUser, BaseUser
from .content import Content, BusContent, BaseContent
from .material import MaterialAnalysisStatus, MaterialClean
from .worker_state import VideoCleanCursor
from .analysis import (
    VideoAnalysisResult,
    VideoAnalysisRun,
    VideoAnalysisRunOrigin,
    VideoAnalysisRunStatus,
    VideoAnalysisStatus,
)
from .prompt_rule import (
    AgentPromptRule,
    AgentPromptRuleVersion,
    AgentPromptRuleVersionStatus,
)
from .comment import Comment, BusComment, BaseComment
from .media import Media, BusMedia, BaseMedia
from .follow import Follow, BusFollow, BaseFollow, FollowBase, FollowSchema, FollowResponse, FollowListResponse
from .relat import Contentrelat, BusContentRelat, BaseContentRelat, BusPostRelation, BasePostRelation
from .platform import (
    platformSource as SiteSource,
    platformSourceBase as SiteSourceBase,
    platformSourceCreate as SiteSourceCreate,
    platformSourceResponse as SiteSourceResponse,
    PlatformStatus,
)
from .action import Action, ActionBase, ActionCreate, ActionUpdate, ActionResponse
from .action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from .tiktok import TkCategory, TkChallenge
from .keyword import BusiSearchKeyword
from .job import JobBase, BusJob, BaseJob
from .llm_provider import LlmModel, LlmProvider, ProviderProtocol
from .datatype import (
    SysDatatype,
    ColumnMeta,
    DtoFieldMeta,
    SysDatatypeBase,
    SysDatatypeRead,
    SysDatatypeList,
    SysDatatypeStatusUpdate,
    SysDatatypeSyncResponse,
    introspect_datatype_models,
)

# ==================== Pydantic Schemas / DTOs ====================
from .base import DataTypeEnum, BaseSchema, TimeMixin, IDMixin, ApiResponse, PageResponse

# User 相关的 Pydantic 实体
from .user import UserBase, UserCreate, UserUpdate, UserResponse, UserListResponse, GenderEnum

# Content 相关的 Pydantic 实体
from .content import ContentBase, ContentCreate, ContentUpdate, ContentResponse, ContentListResponse

# Comment 相关的 Pydantic 实体
from .comment import CommentSchema, CommentResponse, CommentListResponse

# Media 相关的 Pydantic 实体
from .media import MediaSchema, MediaCreate, MediaResponse, MediaListResponse, MediaTypeEnum

# SiteSource 相关的 Pydantic 实体 (already imported above with aliases)

from .task import TaskStatus, BusTask, BusTaskLog

__all__ = [
    # SQLAlchemy ORM 物理模型
    "Base",
    "GeneralBase",
    "BusUser",
    "BaseUser",
    "User",
    "BusContent",
    "BaseContent",
    "Content",
    "MaterialAnalysisStatus",
    "MaterialClean",
    "VideoCleanCursor",
    "VideoAnalysisResult",
    "VideoAnalysisRun",
    "VideoAnalysisRunOrigin",
    "VideoAnalysisRunStatus",
    "VideoAnalysisStatus",
    "AgentPromptRule",
    "AgentPromptRuleVersion",
    "AgentPromptRuleVersionStatus",
    "BusComment",
    "BaseComment",
    "Comment",
    "BusMedia",
    "BaseMedia",
    "Media",
    "BusFollow",
    "BaseFollow",
    "Follow",
    "FollowBase",
    "FollowSchema",
    "FollowResponse",
    "FollowListResponse",
    "BusContentRelat",
    "BaseContentRelat",
    "BusPostRelation",
    "BasePostRelation",
    "Contentrelat",
    "SiteSource",
    "PlatformStatus",
    "BusTaskLog",
    "Action",
    "ActionBase",
    "ActionCreate",
    "ActionUpdate",
    "ActionResponse",
    "ActionParserSample",
    "ActionParserRevision",
    "ActionParserRevisionSample",
    "TkChallenge",
    "TkCategory",
    "BusiSearchKeyword",
    "JobBase",
    "BusJob",
    "BaseJob",
    "LlmModel",
    "LlmProvider",
    "ProviderProtocol",
    "SysDatatype",

    # Pydantic Schemas / DTOs
    "BaseSchema",
    "TimeMixin",
    "IDMixin",
    "ApiResponse",
    "PageResponse",
    "DataTypeEnum",
    "GenderEnum",
    "MediaTypeEnum",
    "ColumnMeta",
    "DtoFieldMeta",
    "SysDatatypeBase",
    "SysDatatypeRead",
    "SysDatatypeList",
    "SysDatatypeStatusUpdate",
    "SysDatatypeSyncResponse",
    "introspect_datatype_models",
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserListResponse",
    "ContentBase",
    "ContentCreate",
    "ContentUpdate",
    "ContentResponse",
    "ContentListResponse",
    "CommentSchema",
    "CommentResponse",
    "CommentListResponse",
    "MediaSchema",
    "MediaCreate",
    "MediaResponse",
    "MediaListResponse",
    "SiteSourceBase",
    "SiteSourceCreate",
    "SiteSourceResponse",
    "TaskStatus",
    "BusTask"
]
