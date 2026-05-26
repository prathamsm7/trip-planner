import type { StreamEvent, TripSnapshot } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function createThread(): Promise<string> {
  const res = await fetch(`${API_URL}/api/threads`, { method: "POST" });
  const data = await res.json();
  return data.thread_id as string;
}

export async function getThread(threadId: string): Promise<{
  snapshot: TripSnapshot | null;
  interrupt: {
    type?: string;
    question?: string;
    index?: number;
    total?: number;
    message?: string;
    questions?: string[];
  } | null;
}> {
  const res = await fetch(`${API_URL}/api/threads/${threadId}`);
  return res.json();
}

export async function patchSelections(
  threadId: string,
  selections: Record<string, unknown>
): Promise<void> {
  await fetch(`${API_URL}/api/threads/${threadId}/selections`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections }),
  });
}

export async function consumeSSE(
  url: string,
  body: object,
  onEvent: (event: StreamEvent) => void
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
  });

  if (!res.ok || !res.body) {
    throw new Error(`Request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const raw = part.trim();
      if (!raw.includes("data:")) continue;
      // Support single or double-wrapped SSE lines from the server.
      const json = raw
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.replace(/^data:\s*/, ""))
        .join("")
        .trim();
      if (!json) continue;
      try {
        onEvent(JSON.parse(json) as StreamEvent);
      } catch {
        /* skip malformed */
      }
    }
  }
}

export function streamMessage(threadId: string, content: string, onEvent: (e: StreamEvent) => void) {
  return consumeSSE(
    `${API_URL}/api/threads/${threadId}/messages`,
    { content },
    onEvent
  );
}

export function streamResume(threadId: string, content: string, onEvent: (e: StreamEvent) => void) {
  return consumeSSE(
    `${API_URL}/api/threads/${threadId}/resume`,
    { content },
    onEvent
  );
}
