BEGIN;

ALTER TABLE public.t_busi_content
    ADD COLUMN IF NOT EXISTS is_download BOOLEAN NOT NULL DEFAULT false;

UPDATE public.t_busi_content AS content
SET is_download = true
WHERE EXISTS (
    SELECT 1
    FROM public.t_busi_media AS media
    WHERE media.platform = content.platform
      AND media.content_id = content.content_id
      AND media.type = 1
      AND COALESCE(media.is_download, 0) = 1
);

ALTER TABLE public.t_busi_media
    DROP COLUMN IF EXISTS is_download;

COMMIT;
