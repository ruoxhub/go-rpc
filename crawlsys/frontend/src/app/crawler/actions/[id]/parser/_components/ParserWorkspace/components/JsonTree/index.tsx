// JsonTree：渲染脱敏样例并返回绝对 JSON Pointer，支持高密度树形浏览、语法高亮、字段搜索与一键复制。
"use client";

import { useState, useEffect, useRef, useMemo, type KeyboardEvent, type ReactNode } from "react";
import { Button } from "@/app/_components/ui/button";
import { Input } from "@/app/_components/ui/input";

import type { JsonValue } from "@/api/action-parser/action-parser.types";
import { pointerJoin } from "../../utils/jsonPointer";

interface JsonTreeProps {
  value: JsonValue;
  recordPath?: string;
  onSelect: (pointer: string) => void;
  toolbar?: boolean;
}

function isBranch(value: JsonValue): value is JsonValue[] | Record<string, JsonValue> {
  return Array.isArray(value) || (typeof value === "object" && value !== null);
}

function childrenOf(value: JsonValue): readonly (readonly [string, JsonValue])[] {
  if (Array.isArray(value)) {
    return value.map((item, index) => [String(index), item] as const);
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value);
  }
  return [] as const;
}

function matchesSearch(label: string, value: JsonValue, query: string): boolean {
  if (!query) return false;
  const q = query.toLowerCase();
  if (label.toLowerCase().includes(q)) return true;
  if (typeof value === "string" && value.toLowerCase().includes(q)) return true;
  if (typeof value === "number" && String(value).includes(q)) return true;
  if (typeof value === "boolean" && String(value).includes(q)) return true;
  return false;
}

function hasMatchingDescendant(value: JsonValue, query: string): boolean {
  if (!query || !isBranch(value)) return false;
  const q = query.toLowerCase();
  if (Array.isArray(value)) {
    return value.some(
      (item, index) =>
        String(index).includes(q) ||
        matchesSearch(String(index), item, q) ||
        hasMatchingDescendant(item, q),
    );
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).some(
      ([k, v]) =>
        k.toLowerCase().includes(q) ||
        matchesSearch(k, v, q) ||
        hasMatchingDescendant(v, q),
    );
  }
  return false;
}

function countMatchingNodes(value: JsonValue, query: string): number {
  if (!query) return 0;
  let count = 0;
  function walk(val: JsonValue, label: string) {
    if (matchesSearch(label, val, query)) {
      count += 1;
    }
    if (Array.isArray(val)) {
      val.forEach((item, index) => walk(item, String(index)));
    } else if (typeof val === "object" && val !== null) {
      Object.entries(val).forEach(([k, v]) => walk(v, k));
    }
  }
  walk(value, "root");
  return count;
}

function HighlightText({ text, query }: { text: string; query: string }) {
  if (!query || !text.toLowerCase().includes(query.toLowerCase())) {
    return <>{text}</>;
  }
  const q = query.toLowerCase();
  const lower = text.toLowerCase();
  const parts: ReactNode[] = [];
  let start = 0;
  let index = lower.indexOf(q, start);

  while (index !== -1) {
    if (index > start) {
      parts.push(text.slice(start, index));
    }
    parts.push(
      <mark
        key={index}
        className="rounded-xs bg-primary/25 px-0.5 text-foreground font-semibold"
      >
        {text.slice(index, index + q.length)}
      </mark>,
    );
    start = index + q.length;
    index = lower.indexOf(q, start);
  }

  if (start < text.length) {
    parts.push(text.slice(start));
  }

  return <>{parts}</>;
}

function Node({
  label,
  value,
  pointer,
  recordPath = "",
  onSelect,
  root = false,
  isParentArray = false,
  searchQuery = "",
  expandSignal = null,
}: {
  label: string;
  value: JsonValue;
  pointer: string;
  recordPath?: string;
  onSelect: (pointer: string) => void;
  root?: boolean;
  isParentArray?: boolean;
  searchQuery?: string;
  expandSignal?: { expanded: boolean; timestamp: number } | null;
}) {
  const branch = isBranch(value);
  const [expanded, setExpanded] = useState(root);
  const [visible, setVisible] = useState(100);

  const type = Array.isArray(value) ? "array" : branch ? "object" : typeof value;
  const toggleName = `${expanded ? "折叠" : "展开"} ${label}（${type}，${pointer || "/"}）`;
  const select = () => onSelect(pointer);

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select();
    }
  };

  useEffect(() => {
    if (expandSignal) {
      setExpanded(expandSignal.expanded);
    }
  }, [expandSignal]);

  useEffect(() => {
    if (searchQuery && hasMatchingDescendant(value, searchQuery)) {
      setExpanded(true);
    }
  }, [searchQuery, value]);

  const isMatched = searchQuery ? matchesSearch(label, value, searchQuery) : false;
  const isRecordPath = Boolean(recordPath && pointer === recordPath);

  const children = useMemo(() => (branch ? childrenOf(value) : []), [branch, value]);

  const renderValuePreview = () => {
    if (branch) {
      const count = children.length;
      if (Array.isArray(value)) {
        if (!expanded) {
          return (
            <span className="text-muted-foreground/70 font-normal">
              [ <span className="text-[11px] text-muted-foreground">{count} 项</span> ]
            </span>
          );
        }
        return <span className="text-muted-foreground font-normal">[</span>;
      }
      if (!expanded) {
        return (
          <span className="text-muted-foreground/70 font-normal">
            &#123; <span className="text-[11px] text-muted-foreground">{count} 属性</span> &#125;
          </span>
        );
      }
      return <span className="text-muted-foreground font-normal">&#123;</span>;
    }

    if (typeof value === "string") {
      const truncated = value.length > 80 ? `${value.slice(0, 80)}…` : value;
      return (
        <span
          className="text-success break-all font-normal"
          title={value.length > 80 ? value : undefined}
        >
          &quot;<HighlightText text={truncated} query={searchQuery} />&quot;
        </span>
      );
    }
    if (typeof value === "number") {
      return (
        <span className="text-warning font-semibold">
          <HighlightText text={String(value)} query={searchQuery} />
        </span>
      );
    }
    if (typeof value === "boolean") {
      return (
        <span className="text-brand-purple font-semibold">
          <HighlightText text={String(value)} query={searchQuery} />
        </span>
      );
    }
    if (value === null) {
      return <span className="text-muted-foreground italic font-normal">null</span>;
    }
    return <span className="text-muted-foreground font-normal">{String(value)}</span>;
  };

  return (
    <li className="flex flex-col">
      <div
        className={`group relative flex items-center gap-1 rounded-sm px-1 py-0.5 text-xs font-mono transition-colors hover:bg-muted/70 ${
          isMatched ? "bg-primary/10 ring-1 ring-primary/30" : ""
        }`}
      >
        {branch ? (
          <button
            type="button"
            aria-expanded={expanded}
            aria-label={toggleName}
            title={toggleName}
            onClick={(event) => {
              event.stopPropagation();
              setExpanded((current) => !current);
            }}
            className="flex h-5 w-5 shrink-0 cursor-pointer items-center justify-center rounded text-muted-foreground transition-transform hover:bg-accent hover:text-foreground"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transition-transform duration-150 ${expanded ? "rotate-90" : ""}`}
              aria-hidden="true"
            >
              <path d="m9 18 6-6-6-6" />
            </svg>
          </button>
        ) : (
          <span className="w-5 shrink-0" aria-hidden="true" />
        )}

        <button
          type="button"
          aria-label={`选择节点 ${pointer || "/"}`}
          title={`点击选择节点 ${pointer || "/"}`}
          onClick={select}
          onKeyDown={onKeyDown}
          className="flex min-w-0 flex-1 cursor-pointer items-center gap-1.5 text-left"
        >
          {root ? (
            <span className="font-semibold text-foreground">root</span>
          ) : isParentArray ? (
            <span className="text-muted-foreground font-normal">
              [<HighlightText text={label} query={searchQuery} />]:
            </span>
          ) : (
            <span className="font-medium text-info">
              &quot;<HighlightText text={label} query={searchQuery} />&quot;:
            </span>
          )}

          {renderValuePreview()}

          {isRecordPath ? (
            <span className="ml-1 inline-flex items-center rounded border border-primary/20 bg-primary/15 px-1.5 py-0.2 text-[10px] font-sans font-medium text-primary">
              记录根路径
            </span>
          ) : null}

          <span className="ml-auto rounded bg-background/80 px-1 py-0.2 text-[10px] font-sans text-muted-foreground/60 opacity-0 transition-opacity group-hover:opacity-100">
            {pointer || "/"}
          </span>
        </button>
      </div>

      {branch && expanded ? (
        <div className="flex flex-col">
          <ul className="ml-2.5 flex flex-col border-l border-border/60 pl-3">
            {children.slice(0, visible).map(([childLabel, childValue]) => (
              <Node
                key={pointerJoin(pointer, childLabel)}
                label={childLabel}
                value={childValue}
                pointer={pointerJoin(pointer, childLabel)}
                recordPath={recordPath}
                onSelect={onSelect}
                isParentArray={Array.isArray(value)}
                searchQuery={searchQuery}
                expandSignal={expandSignal}
              />
            ))}
            {visible < children.length ? (
              <li className="py-1">
                <button
                  type="button"
                  onClick={() => setVisible((current) => current + 100)}
                  className="cursor-pointer text-xs text-primary underline hover:opacity-80"
                >
                  显示更多节点（剩余 {children.length - visible} 项）
                </button>
              </li>
            ) : null}
          </ul>
          <div className="pl-6 text-xs font-mono text-muted-foreground/60 leading-5">
            {Array.isArray(value) ? "]" : "}"}
          </div>
        </div>
      ) : null}
    </li>
  );
}

export function JsonTree({
  value,
  recordPath = "",
  onSelect,
  toolbar = true,
}: JsonTreeProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [expandSignal, setExpandSignal] = useState<{
    expanded: boolean;
    timestamp: number;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      clearTimeout(copyTimer.current ?? undefined);
    };
  }, []);

  const matchCount = useMemo(
    () => (searchQuery ? countMatchingNodes(value, searchQuery) : 0),
    [value, searchQuery],
  );

  const handleCopyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(value, null, 2));
      setCopied(true);
      clearTimeout(copyTimer.current ?? undefined);
      copyTimer.current = window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // 剪贴板不可用时静默处理
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {toolbar ? (
        <div className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-2 border-b border-border bg-card/90 pb-2 backdrop-blur-xs">
          <div className="flex flex-1 items-center gap-1.5 min-w-[180px] max-w-xs">
            <div className="relative flex w-full items-center">
              <span className="pointer-events-none absolute left-2 text-muted-foreground">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
              </span>
              <Input
                type="text"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="搜索字段名或数值…"
                className="h-7 w-full bg-background pl-6 pr-6 text-xs"
              />
              {searchQuery ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setSearchQuery("")}
                  className="absolute right-1 h-5 w-5 p-0 text-xs text-muted-foreground hover:text-foreground"
                  aria-label="清空搜索"
                >
                  ×
                </Button>
              ) : null}
            </div>
            {searchQuery ? (
              <span className="shrink-0 text-[11px] text-muted-foreground">
                {matchCount > 0 ? `${matchCount} 处匹配` : "无匹配"}
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-1.5 text-xs">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setExpandSignal({ expanded: true, timestamp: Date.now() })}
              className="h-7 px-2 text-xs"
            >
              全部展开
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setExpandSignal({ expanded: false, timestamp: Date.now() })}
              className="h-7 px-2 text-xs"
            >
              全部折叠
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleCopyJson}
              className="h-7 gap-1 px-2 text-xs"
            >
              {copied ? (
                <>
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-success"
                    aria-hidden="true"
                  >
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                  <span className="text-success">已复制</span>
                </>
              ) : (
                <>
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                    <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                  </svg>
                  <span>复制 JSON</span>
                </>
              )}
            </Button>
          </div>
        </div>
      ) : null}

      <ul className="flex flex-col gap-0.5" aria-label="脱敏 JSON 树">
        <Node
          label="root"
          value={value}
          pointer=""
          recordPath={recordPath}
          onSelect={onSelect}
          root
          searchQuery={searchQuery}
          expandSignal={expandSignal}
        />
      </ul>
    </div>
  );
}
