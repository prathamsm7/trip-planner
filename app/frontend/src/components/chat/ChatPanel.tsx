"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage, StepEvent } from "@/lib/types";
import { TripPackageCard } from "@/components/package/TripPackageCard";
import { MarkdownMessage } from "@/components/chat/MarkdownMessage";

interface Props {
  messages: ChatMessage[];
  steps: StepEvent[];
  isStreaming: boolean;
  isLoading: boolean;
  showPackageCard: boolean;
  onSend: (text: string) => void;
  onPackageSelect: (tab: "itinerary" | "flights" | "trains" | "hotels" | "package") => void;
  structured?: Record<string, unknown>;
}

export function ChatPanel({
  messages,
  steps,
  isStreaming,
  isLoading,
  showPackageCard,
  onSend,
  onPackageSelect,
  structured,
}: Props) {
  const dest = (structured?.destinationLocation as string) ?? "Trip";
  const source = (structured?.sourceLocation as string) ?? "";
  const dr = structured?.date_range as { start?: string; end?: string } | undefined;
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages, steps, isStreaming]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden chat-bg border-r border-gray-200">
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-4 py-6 space-y-4"
      >
        {isLoading ? (
          <div
            className="flex h-full min-h-[12rem] items-center justify-center"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span className="h-4 w-4 rounded-full border-2 border-gray-300 border-t-safar-navy animate-spin" />
              Loading conversation…
            </div>
          </div>
        ) : (
          messages.map((m) =>
            m.content.trim() ? (
            <div
              key={m.id}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[90%] rounded-2xl px-4 py-3 ${
                  m.role === "user"
                    ? "bg-safar-navy text-white text-sm leading-relaxed whitespace-pre-wrap"
                    : "bg-white border border-gray-200 shadow-sm"
                }`}
              >
                {m.role === "assistant" && (
                  <p className="text-xs font-semibold text-safar-red mb-2">Safar AI</p>
                )}
                {m.role === "assistant" ? (
                  <MarkdownMessage content={m.content} />
                ) : (
                  m.content
                )}
              </div>
            </div>
            ) : null
          )
        )}

        {!isLoading && isStreaming && steps.length > 0 && (
          <div className="bg-white border border-gray-200 rounded-xl p-3 shadow-sm">
            <p className="text-xs font-semibold text-gray-500 mb-2">Working on your trip</p>
            <ul className="space-y-1.5">
              {steps.map((s) => (
                <li key={s.step_id || s.node} className="flex items-center gap-2 text-sm">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      s.status === "done" ? "bg-green-500" : "bg-amber-400 animate-pulse"
                    }`}
                  />
                  <span className={s.status === "done" ? "text-gray-600" : "text-gray-900"}>
                    {s.description || s.label}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="shrink-0 flex flex-col bg-white border-t border-gray-200">
        {showPackageCard && structured && (
          <TripPackageCard
            destination={dest}
            source={source}
            dateStart={dr?.start}
            dateEnd={dr?.end}
            onSelect={onPackageSelect}
          />
        )}
        <div className="p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const text = (fd.get("message") as string)?.trim();
              if (text) {
                onSend(text);
                e.currentTarget.reset();
              }
            }}
          >
            <div className="flex gap-2">
              <input
                name="message"
                disabled={isStreaming || isLoading}
                placeholder={isLoading ? "Loading conversation…" : "Type your question here..."}
                className="flex-1 rounded-full border border-gray-300 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-safar-navy/30"
              />
              <button
                type="submit"
                disabled={isStreaming || isLoading}
                className="shrink-0 rounded-full bg-safar-red px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Send
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
