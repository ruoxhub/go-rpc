"use client";

import { useRouter } from "next/navigation";
import { Select } from "./ui/select";

export interface VideoOption {
  id: string;
  label: string;
}

/** 分析结果切换器：通过 ?id= 查询参数切换，保持服务端渲染数据流 */
export function VideoSelect({
  options,
  value,
}: {
  options: VideoOption[];
  value: string;
}) {
  const router = useRouter();
  if (options.length <= 1) return null;
  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      切换视频
      <Select
        value={value}
        onChange={(event) =>
          router.push(`?id=${encodeURIComponent(event.target.value)}`)
        }
        className="w-auto cursor-pointer bg-background"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </Select>
    </label>
  );
}
