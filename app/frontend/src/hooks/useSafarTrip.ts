"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createThread,
  getThread,
  patchSelections,
  streamMessage,
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
        const { snapshot: snap } = await getThread(id);
        if (snap) {
          setSnapshot(snap);
          if (snap.itinerary) setShowPackageCard(true);
          if (snap.selections) setSelections(snap.selections as Selections);
          if (snap.messages && snap.messages.length > 0) {
            setMessages(
              snap.messages.map((m) => ({
                id: uid(),
                role: m.role === "user" ? "user" : "assistant",
                content: m.content,
              }))
            );
          }
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
        const key = event.step_id || event.node!;
        const exists = prev.find(
          (s) => (s.step_id || s.node) === key && s.status === "running"
        );
        if (exists) return prev;
        return [
          ...prev,
          {
            node: event.node!,
            step_id: event.step_id,
            label: event.label!,
            description: event.description,
            status: "running",
          },
        ];
      });
    }
    if (event.type === "step_complete" && event.node) {
      setSteps((prev) =>
        prev.map((s) => {
          const key = event.step_id || event.node!;
          if ((s.step_id || s.node) !== key && s.node !== event.node) return s;
          if (event.step_id && s.step_id && s.step_id !== event.step_id) return s;
          return {
            ...s,
            status: "done",
            description: event.description || s.description,
          };
        })
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
    if (event.type === "done" && event.snapshot) {
      const prev = preStreamSnapshot.current;
      setSnapshot(event.snapshot);

      const itineraryIsNew = event.snapshot.itinerary && !prev?.itinerary;
      const fd = event.snapshot.flights_data as Record<string, unknown> | undefined;
      const prevFd = prev?.flights_data as Record<string, unknown> | undefined;
      const flightsAreNew =
        !!fd &&
        "outbound" in fd &&
        !(prevFd && "outbound" in prevFd);
      const hotelsAreNew =
        event.snapshot.hotel_search_results != null && prev?.hotel_search_results == null;

      // Tab/package UI only — chat copy comes from the model stream.
      if (itineraryIsNew || flightsAreNew || hotelsAreNew) {
        setShowPackageCard(true);
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
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!threadId || !content.trim() || isStreaming) return;
      preStreamSnapshot.current = snapshot;
      setMessages((prev) => [...prev, { id: uid(), role: "user", content: content.trim() }]);
      setIsStreaming(true);
      setSteps([]);

      try {
        await streamMessage(threadId, content.trim(), handleEvent);
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
    [threadId, isStreaming, handleEvent]
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
