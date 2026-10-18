import type { JsonValue } from "@/api/action-parser/action-parser.types";

export function encodePointer(tokens: string[]) {
  if (tokens.length === 0) return "";
  return `/${tokens
    .map((token) => token.replaceAll("~", "~0").replaceAll("/", "~1"))
    .join("/")}`;
}

export function pointerJoin(pointer: string, token: string) {
  return encodePointer([...decodePointer(pointer), token]);
}

export function decodePointer(pointer: string) {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) throw new Error("pointer must be absolute");
  return pointer
    .slice(1)
    .split("/")
    .map((token) => {
      if (/~(?:[^01]|$)/.test(token)) {
        throw new Error("invalid pointer escape");
      }
      return token.replaceAll("~1", "/").replaceAll("~0", "~");
    });
}

export function resolvePointer(root: JsonValue, pointer: string) {
  let current: JsonValue | undefined = root;
  for (const token of decodePointer(pointer)) {
    if (Array.isArray(current)) {
      if (!/^(0|[1-9]\d*)$/.test(token)) return undefined;
      current = current[Number(token)];
    } else if (
      current !== null &&
      typeof current === "object" &&
      Object.hasOwn(current, token)
    ) {
      current = current[token];
    } else {
      return undefined;
    }
  }
  return current;
}

export function representativeRecord(root: JsonValue, recordPath: string) {
  const value = resolvePointer(root, recordPath);
  if (Array.isArray(value)) {
    return value.length === 0
      ? null
      : {
          value: value[0],
          absoluteBase: encodePointer([
            ...decodePointer(recordPath),
            "0",
          ]),
        };
  }
  return value !== null && typeof value === "object"
    ? { value, absoluteBase: recordPath }
    : null;
}

export function relativePointer(
  absoluteBase: string,
  absoluteNode: string,
) {
  const base = decodePointer(absoluteBase);
  const node = decodePointer(absoluteNode);
  if (base.some((token, index) => node[index] !== token)) return null;
  return encodePointer(node.slice(base.length));
}
