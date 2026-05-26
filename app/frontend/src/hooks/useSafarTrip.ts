"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createThread,
  getThread,
  patchSelections,
  streamMessage,
  streamResume,
} from "@/lib/api";
import type {
  ChatMessage,
  FlightsData,
  HotelProperty,
  Itinerary,
  Selections,
  StepEvent,
  StreamEvent,
  TabId,
  TripSnapshot,
  WeatherOutlook,
} from "@/lib/types";

const THREAD_KEY = "safar_thread_id";

function uid() {
  return Math.random().toString(36).slice(2);
}

function mergeSnapshot(prev: TripSnapshot | null, patch: Record<string, unknown>): TripSnapshot {
  return { ...(prev ?? {}), ...patch } as TripSnapshot;
}

export function useSafarTrip() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: uid(),
      role: "assistant",
      content:
        "Hi! I'm Safar AI. Tell me about your trip — where you want to go, when, and who's traveling.",
    },
  ]);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [snapshot, setSnapshot] = useState<TripSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("itinerary");
  const [itinerarySubTab, setItinerarySubTab] = useState<"overview" | "daily">("overview");
  const [selections, setSelections] = useState<Selections>({});
  const [showPackageCard, setShowPackageCard] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [interrupt, setInterrupt] = useState<{
    question?: string;
    index?: number;
    total?: number;
    questions?: string[];
    message?: string;
  } | null>(null);
  const initRef = useRef(false);
  const preStreamSnapshot = useRef<TripSnapshot | null>(null);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    (async () => {
      let id = localStorage.getItem(THREAD_KEY);
      if (!id) {
        id = await createThread();
        localStorage.setItem(THREAD_KEY, id);
      }
      setThreadId(id);
      try {
        const { snapshot: snap, interrupt: intr } = await getThread(id);
        if (snap) {
          setSnapshot(snap);
          if (snap.itinerary) setShowPackageCard(true);
          if (snap.selections) setSelections(snap.selections as Selections);
        }
        if (intr?.question || intr?.questions?.length) setInterrupt(intr);
        if (intr?.message) {
          setMessages((prev) => [
            ...prev,
            { id: uid(), role: "assistant", content: intr.message!, kind: "interrupt" },
          ]);
        }
      } catch {
        const newId = await createThread();
        localStorage.setItem(THREAD_KEY, newId);
        setThreadId(newId);
      }
    })();
  }, []);

  const handleEvent = useCallback((event: StreamEvent) => {
    if (event.type === "step_start" && event.node && event.label) {
      setSteps((prev) => {
        const exists = prev.find((s) => s.node === event.node && s.status === "running");
        if (exists) return prev;
        return [...prev, { node: event.node!, label: event.label!, status: "running" }];
      });
    }
    if (event.type === "step_complete" && event.node) {
      setSteps((prev) =>
        prev.map((s) => (s.node === event.node ? { ...s, status: "done" } : s))
      );
      if (event.payload) {
        setSnapshot((prev) => mergeSnapshot(prev, event.payload as Record<string, unknown>));
      }
      if (event.ui_hints?.open_tab) {
        setActiveTab(event.ui_hints.open_tab);
      }
      if (event.ui_hints?.show_package_card) {
        setShowPackageCard(true);
      }
    }
    if (event.type === "package_ready") {
      setShowPackageCard(true);
    }
    if (event.type === "message" && event.content) {
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "assistant", content: event.content! },
      ]);
    }
    if (event.type === "interrupt") {
      setInterrupt({
        question: event.question,
        index: event.index,
        total: event.total,
        questions: event.questions,
        message: event.message,
      });
      const text =
        event.message ??
        (event.question
          ? event.question
          : `I need a few more details:\n${(event.questions ?? []).map((q) => `- ${q}`).join("\n")}`);
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && last.kind === "interrupt" && last.content === text) {
          return prev;
        }
        return [
          ...prev,
          { id: uid(), role: "assistant", content: text, kind: "interrupt" },
        ];
      });
    }
    if (event.type === "done" && event.snapshot) {
      const prev = preStreamSnapshot.current;
      setSnapshot(event.snapshot);
      setInterrupt(null);

      const itineraryIsNew = event.snapshot.itinerary && !prev?.itinerary;
      const fd = event.snapshot.flights_data as Record<string, unknown> | undefined;
      const prevFd = prev?.flights_data as Record<string, unknown> | undefined;
      const flightsAreNew = fd && "best_flights" in fd && !(prevFd && "best_flights" in prevFd);
      const hotelsAreNew =
        event.snapshot.hotel_search_results != null && prev?.hotel_search_results == null;

      if (itineraryIsNew) {
        setShowPackageCard(true);
        const summary =
          (event.snapshot.itinerary as { summary?: string })?.summary ??
          "Your trip plan is ready. Open the itinerary tab on the right to explore details.";
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "assistant", content: summary, kind: "text" },
        ]);
      } else if (flightsAreNew) {
        const hasFlights =
          ((fd?.best_flights as unknown[]) ?? []).length > 0 ||
          ((fd?.other_flights as unknown[]) ?? []).length > 0;
        setShowPackageCard(true);
        if (hasFlights) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              content: "Flight options are ready — check the flights tab on the right.",
            },
          ]);
        }
      } else if (hotelsAreNew) {
        setShowPackageCard(true);
        if (event.snapshot.hotel_search_results!.length > 0) {
          setMessages((prev) => [
            ...prev,
            {
              id: uid(),
              role: "assistant",
              content: "Hotel options are ready — check the hotels tab on the right.",
            },
          ]);
        }
      }
    }
    if (event.type === "error") {
      setMessages((prev) => [
        ...prev,
        {
          id: uid(),
          role: "assistant",
          content: event.message ?? "Something went wrong. Please try again.",
        },
      ]);
    }
  }, [showPackageCard]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!threadId || !content.trim() || isStreaming) return;
      preStreamSnapshot.current = snapshot;
      setMessages((prev) => [...prev, { id: uid(), role: "user", content: content.trim() }]);
      setIsStreaming(true);
      setSteps([]);

      try {
        const runner = interrupt
          ? streamResume(threadId, content.trim(), handleEvent)
          : streamMessage(threadId, content.trim(), handleEvent);
        await runner;
      } catch (e) {
        const msg =
          e instanceof Error && e.message.length < 200
            ? e.message
            : "Unable to reach the planner. Check that the API is running and try again.";
        setMessages((prev) => [
          ...prev,
          { id: uid(), role: "assistant", content: msg },
        ]);
      } finally {
        setIsStreaming(false);
      }
    },
    [threadId, isStreaming, interrupt, handleEvent]
  );

  const updateSelections = useCallback(
    async (next: Selections) => {
      setSelections(next);
      if (threadId) {
        await patchSelections(threadId, next as Record<string, unknown>);
      }
    },
    [threadId]
  );

  const newTrip = useCallback(async () => {
    const id = await createThread();
    localStorage.setItem(THREAD_KEY, id);
    setThreadId(id);
    setSnapshot(null);
    setSteps([]);
    setSelections({});
    setShowPackageCard(false);
    setInterrupt(null);
    setActiveTab("itinerary");
    setMessages([
      {
        id: uid(),
        role: "assistant",
        content: "Starting a fresh trip. Where would you like to go?",
      },
    ]);
  }, []);

  return {
    threadId,
    messages,
    steps,
    snapshot,
    activeTab,
    setActiveTab,
    itinerarySubTab,
    setItinerarySubTab,
    selections,
    updateSelections,
    showPackageCard,
    isStreaming,
    interrupt,
    sendMessage,
    newTrip,
    structured: snapshot?.structured as Record<string, unknown> | undefined,
    itinerary: snapshot?.itinerary as Itinerary | undefined,
    weather: snapshot?.weather as WeatherOutlook | undefined,
    destinationAbout: snapshot?.destination_about ?? "",
    flights: snapshot?.flights_data as FlightsData | undefined,
    hotels: (snapshot?.hotel_search_results ?? null) as HotelProperty[] | null,
  };
}
