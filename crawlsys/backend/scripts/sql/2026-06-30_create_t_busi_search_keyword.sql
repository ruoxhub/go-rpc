-- 平台搜索关键词常量表
CREATE TABLE IF NOT EXISTS public.t_busi_search_keyword (
    id          BIGSERIAL    PRIMARY KEY,
    platform    VARCHAR(100) NOT NULL,
    keyword     TEXT         NOT NULL,
    is_crawled  BOOLEAN      NOT NULL DEFAULT false,
    created_at  TIMESTAMP    NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.t_busi_search_keyword IS '平台搜索关键词常量；任务配置把 ref_table 选为此表时，Worker 按 platform 全量读取，每行一个 WorkItem。';
COMMENT ON COLUMN public.t_busi_search_keyword.platform   IS '关联 t_busi_platform.bs_platform_code';
COMMENT ON COLUMN public.t_busi_search_keyword.keyword    IS '关键词文本';
COMMENT ON COLUMN public.t_busi_search_keyword.created_at IS '创建时间';

ALTER TABLE public.t_busi_search_keyword
    ADD COLUMN IF NOT EXISTS is_crawled BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN public.t_busi_search_keyword.is_crawled IS '是否已抓取完成（Worker mark_done 标记）';

CREATE INDEX IF NOT EXISTS idx_bsk_platform
    ON public.t_busi_search_keyword (platform);

ALTER TABLE public.t_busi_search_keyword
    ADD CONSTRAINT fk_bsk_platform
    FOREIGN KEY (platform)
    REFERENCES public.t_busi_platform (bs_platform_code);
