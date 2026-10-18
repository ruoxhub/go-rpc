"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, Check } from "lucide-react";
import { Button } from "./ui/button";

/** Outline 风格复制按钮，文案不变、图标反馈 */
export function CopyButton({
  text,
  label = "复制",
  className,
}: {
  text?: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  if (!text) return null;

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          if (timer.current) clearTimeout(timer.current);
          timer.current = setTimeout(() => setCopied(false), 1500);
        } catch {
          // 剪贴板不可用时静默失败
        }
      }}
      className={className}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? "已复制" : label}
    </Button>
  );
}
