export function ensureStringMessage(value: unknown): string {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (typeof value === "object") {
    console.error("Non-string assistant message:", value);
    return "I completed the action, but had trouble formatting the response.";
  }
  return String(value);
}

