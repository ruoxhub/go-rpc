"""Read-only video material analysis endpoints."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from api.analysis.repository import AnalysisRepository, STATUS_VALUES, _item
from api.analysis.schemas import AnalysisFilters, MaterialAnalysisDetail, MaterialAnalysisList, VideoAnalysisRead, VideoUrlResponse
from services.video_download.naming import cover_object_name, video_object_name
from api.deps import get_db, get_minio

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("", response_model=MaterialAnalysisList)
async def list_materials(page: int = Query(1, ge=1), page_size: int = Query(20), platform: str | None = None, status: str | None = None, model: str | None = None, db=Depends(get_db)):
    if page_size not in {20, 40, 60}:
        raise HTTPException(422, "page_size 仅支持 20、40 或 60")
    if status and status not in STATUS_VALUES:
        raise HTTPException(422, "分析状态无效")
    items, total, total_pages = await AnalysisRepository(db).list(page=page, page_size=page_size, platform=platform, status=status, model=model)
    return MaterialAnalysisList(items=items, page=page, page_size=page_size, total=total, total_pages=total_pages)


@router.get("/filters", response_model=AnalysisFilters)
async def get_filters(db=Depends(get_db)):
    platforms, statuses, models = await AnalysisRepository(db).filters()
    return AnalysisFilters(platforms=platforms, statuses=statuses, models=models)


@router.get("/{platform}/{content_id}", response_model=MaterialAnalysisDetail)
async def get_detail(platform: str, content_id: str, db=Depends(get_db)):
    row = await AnalysisRepository(db).detail(platform, content_id)
    if not row:
        raise HTTPException(404, "素材不存在")
    material, analysis = row
    return MaterialAnalysisDetail(**_item(material, analysis).model_dump(), analysis=VideoAnalysisRead.model_validate(analysis) if analysis else None)


@router.get("/{platform}/{content_id}/video-url", response_model=VideoUrlResponse)
async def get_video_url(platform: str, content_id: str, db=Depends(get_db), minio=Depends(get_minio)):
    row = await AnalysisRepository(db).detail(platform, content_id)
    if not row:
        raise HTTPException(404, "素材不存在")
    analysis = row[1]
    bucket = platform
    object_name = video_object_name(content_id)
    if not await minio.aobject_exists(bucket, object_name):
        if (
            analysis is None
            or not analysis.minio_object_name
            or not await minio.aobject_exists(
                analysis.minio_bucket, analysis.minio_object_name
            )
        ):
            raise HTTPException(404, "分析视频不存在")
        bucket = analysis.minio_bucket
        object_name = analysis.minio_object_name
    expires = timedelta(hours=1)
    try:
        url = await minio.apresigned_get_object(bucket, object_name, expires=expires)
    except Exception:
        raise HTTPException(502, "视频地址生成失败") from None
    return VideoUrlResponse(url=url, expires_at=datetime.now(timezone.utc) + expires)


@router.get("/{platform}/{content_id}/thumbnail", response_class=RedirectResponse)
async def get_thumbnail(platform: str, content_id: str, db=Depends(get_db), minio=Depends(get_minio)):
    row = await AnalysisRepository(db).detail(platform, content_id)
    if not row:
        raise HTTPException(404, "素材不存在")
    if platform != "tiktok":
        raise HTTPException(404, "素材封面不存在")
    object_name = cover_object_name(content_id)
    if not await minio.aobject_exists(platform, object_name):
        raise HTTPException(404, "素材封面尚未同步")
    url = await minio.apresigned_get_object(platform, object_name, expires=timedelta(hours=1))
    return RedirectResponse(url)
