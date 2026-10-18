/** 展示层格式化工具（纯函数，服务端/客户端均可使用） */

/** 秒数 → "1.5s" 或 "1:05" */
export function formatSeconds(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "-";
  if (value >= 60) {
    const minutes = Math.floor(value / 60);
    const seconds = Math.round(value - minutes * 60);
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }
  return `${value.toFixed(1)}s`;
}

/** 0~1 置信度 → "93%" */
export function formatPercent(ratio?: number | null): string {
  if (ratio == null || Number.isNaN(ratio)) return "-";
  return `${Math.round(ratio * 100)}%`;
}

/** ISO 时间 → 中文本地时间 */
export function formatDateTime(iso?: string): string {
  if (!iso) return "-";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const LANGUAGE_LABELS: Record<string, string> = {
  zh: "中文",
  en: "英语",
  es: "西班牙语",
  ja: "日语",
  ko: "韩语",
  fr: "法语",
  de: "德语",
};

export function languageLabel(code?: string): string {
  if (!code) return "-";
  return LANGUAGE_LABELS[code.toLowerCase()] ?? code;
}

const EMOTION_LABELS: Record<string, string> = {
  curiosity: "好奇",
  satisfaction: "满足",
  confidence: "自信",
  desire: "渴望",
  reassurance: "安心",
  surprise: "惊喜",
  excitement: "兴奋",
  trust: "信任",
  joy: "愉悦",
  urgency: "紧迫感",
};

export function emotionLabel(emotion?: string): string {
  if (!emotion) return "-";
  return EMOTION_LABELS[emotion.toLowerCase()] ?? emotion;
}

const PLATFORM_LABELS: Record<string, string> = {
  tiktok: "TikTok",
  ig_reels: "Instagram Reels",
  xiaohongshu: "小红书",
  youtube_shorts: "YouTube Shorts",
  kuaishou: "快手",
};

export function platformLabel(key?: string): string {
  if (!key) return "-";
  return PLATFORM_LABELS[key.toLowerCase()] ?? key;
}

const SEVERITY_META: Record<string, { label: string; variant: "warning" | "destructive" | "info" }> = {
  minor: { label: "轻微", variant: "warning" },
  moderate: { label: "中等", variant: "info" },
  major: { label: "严重", variant: "destructive" },
};

export function severityMeta(severity?: string) {
  if (!severity) return { label: "-", variant: "info" as const };
  return (
    SEVERITY_META[severity.toLowerCase()] ?? {
      label: severity,
      variant: "info" as const,
    }
  );
}
