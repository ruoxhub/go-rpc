"""Persistent state owned by media workers."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VideoCleanCursor(Base):
    __tablename__ = "t_video_clean_cursor"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    consumer_key: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    watermark_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    watermark_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index(
            "uq_video_clean_cursor_consumer_platform",
            "consumer_key",
            "platform",
            unique=True,
        ),
        {"schema": "public"},
    )
