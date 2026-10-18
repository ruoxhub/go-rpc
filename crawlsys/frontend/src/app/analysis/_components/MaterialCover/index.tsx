"use client";

import { useState } from "react";

interface MaterialCoverProps {
  alt: string;
  placeholderLabel: string;
  src?: string;
}

export function MaterialCover({ alt, placeholderLabel, src }: MaterialCoverProps) {
  const [failed, setFailed] = useState(false);

  return (
    <div className="absolute inset-0 grid place-items-center">
      <div className="grid size-16 place-items-center rounded-full border border-border bg-background/80 text-xs font-semibold text-muted-foreground" aria-hidden={Boolean(src) && !failed}>
        {placeholderLabel}
      </div>
      {src && !failed ? (
        // 平台封面来自动态外部域名，无法使用 Next Image 的静态远程域名白名单。
        // eslint-disable-next-line @next/next/no-img-element
        <img
          alt={alt}
          className="absolute inset-0 size-full object-cover"
          decoding="async"
          loading="lazy"
          onError={() => setFailed(true)}
          src={src}
        />
      ) : null}
    </div>
  );
}
