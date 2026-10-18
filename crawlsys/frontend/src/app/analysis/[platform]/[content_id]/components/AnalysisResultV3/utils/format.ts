import type { TimeRangeV3 } from "../types";

const LOCAL_PATH = /^(?:[a-z]:[\\/]|\\\\|\/)/i;
const SECRET_VALUE = /^(?:bearer\s+|sk[-_]|pk[-_]|api[-_]?key)|(?:api[-_]?key\s*[:=])/i;

export function safeIdentifier(value: string | null) {
  if (!value) return { value: null, hidden: false };
  const normalized = value.trim();
  if (LOCAL_PATH.test(normalized) || SECRET_VALUE.test(normalized)) {
    return { value: null, hidden: true };
  }
  if (normalized.length <= 96) return { value: normalized, hidden: false };
  return {
    value: `${normalized.slice(0, 64)}…${normalized.slice(-24)}`,
    hidden: false,
  };
}

export function formatSeconds(value: number) {
  return `${value.toFixed(2)}s`;
}

export function formatScore(value: number | null) {
  return value == null ? null : value.toFixed(1);
}

export function formatConfidence(value: number | null) {
  return value == null ? null : `${Math.round(value * 100)}%`;
}

export function formatRange(range: TimeRangeV3) {
  const start = range.start_inclusive ? "[" : "(";
  const end = range.end_inclusive ? "]" : ")";
  return `${start}${formatSeconds(range.start_seconds)}, ${formatSeconds(range.end_seconds)}${end}`;
}
