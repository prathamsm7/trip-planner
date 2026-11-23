"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  createThread,
  getThread,
  patchSelections,
  streamMessage,
  listTrips,
  deleteTrip,
  type SavedTripMetadata,
} from "@/lib/api";
import { capSelections } from "@/lib/selectionCaps";
import type {
  ChatMessage,
  FlightsData,
  HotelProperty,
  Itinerary,
  Selections,
  StepEvent,
  StreamEvent,
  TabId,
  TrainsData,
  TripSnapshot,
  WeatherOutlook,
} from "@/lib/types";

const THREAD_KEY = "safar_thread_id";
const SUMMARY_PREFIX = "here is a summary of the conversation to date:";

function isConversationMessage(message: { role: string; content: string }) {
  const content = message.content.trim();
  if (!content) return false;
  if (content.toLowerCase().startsWith(SUMMARY_PREFIX)) return false;
  if (content.toLowerCase().startsWith("current trip (checkpoint context):")) return false;
  return message.role === "user" || message.role === "assistant";
}

const greeting = (): ChatMessage => ({
  id: uid(),
  role: "assistant",
  content:
    "Hi! I'm Safar AI. Tell me about your trip — where you want to go, when, and who's traveling.",
});

function uid() {
  return Math.random().toString(36).slice(2);
}

function mergeSnapshot(prev: TripSnapshot | null, patch: Record<string, unknown>): TripSnapshot {
  return { ...(prev ?? {}), ...patch } as TripSnapshot;
}

interface CachedThread {
  messages: ChatMessage[];
  snapshot: TripSnapshot | null;
  selections: Selections;
  showPackageCard: boolean;
  activeTab: TabId;
  itinerarySubTab: "overview" | "daily";
}

export function useSafarTrip() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [snapshot, setSnapshot] = useState<TripSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("itinerary");
  const [itinerarySubTab, setItinerarySubTab] = useState<"overview" | "daily">("overview");
  const [selections, setSelections] = useState<Selections>({});
  const [awaitingPlanUpdate, setAwaitingPlanUpdate] = useState(false);
  const [showPackageCard, setShowPackageCard] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoadingThread, setIsLoadingThread] = useState(true);
  const [savedTrips, setSavedTrips] = useState<SavedTripMetadata[]>([]);
  const initRef = useRef(false);
  const loadSeq = useRef(0);
  const preStreamSnapshot = useRef<TripSnapshot | null>(null);
  const threadCache = useRef(new Map<string, CachedThread>());
  const allowCacheWrite = useRef(true);

  const refreshSavedTrips = useCallback(async () => {
    try {
      const res = await listTrips();
      setSavedTrips(res.trips || []);
    } catch (e) {
      console.error("Failed to load saved trips", e);
    }
  }, []);

  const loadThread = useCallback(async (id: string) => {
    const seq = ++loadSeq.current;
    const cached = threadCache.current.get(id);
    setThreadId(id);
    setAwaitingPlanUpdate(false);
    localStorage.setItem(THREAD_KEY, id);
    if (cached) {
      allowCacheWrite.current = true;
      setMessages(cached.messages);
      setSteps([]);
      setSnapshot(cached.snapshot);
      setSelections(capSelections(cached.selections));
      setShowPackageCard(cached.showPackageCard);
      setActiveTab(cached.activeTab);
      setItinerarySubTab(cached.itinerarySubTab);
      setIsLoadingThread(false);
      return;
    }

    setIsLoadingThread(true);
    setMessages([]);
    setSteps([]);
    setSnapshot(null);
    setSelections({});
    setShowPackageCard(false);
    try {
      const { snapshot: snap } = await getThread(id);
      const view: CachedThread = snap
        ? {
            snapshot: snap,
            showPackageCard: !!snap.itinerary,
            selections: (snap.selections as Selections) || {},
            activeTab: "itinerary",
            itinerarySubTab: "overview",
            messages: (() => {
              const visible = (snap.messages || []).filter(isConversationMessage);
              return visible.length > 0
                ? visible.map((m) => ({
                    id: uid(),
                    role: m.role === "user" ? ("user" as const) : ("assistant" as const),
                    content: m.content,
                  }))
                : [greeting()];
            })(),
          }
        : {
            snapshot: null,
            showPackageCard: false,
            selections: {},
            activeTab: "itinerary",
            itinerarySubTab: "overview",
            messages: [greeting()],
          };
      threadCache.current.set(id, view);
      if (seq !== loadSeq.current) return;
      allowCacheWrite.current = true;
      setSnapshot(view.snapshot);
      setShowPackageCard(view.showPackageCard);
      setSelections(capSelections(view.selections));
      setActiveTab(view.activeTab);
      setItinerarySubTab(view.itinerarySubTab);
      setMessages(view.messages);
    } catch (e) {
      if (seq !== loadSeq.current) return;
      allowCacheWrite.current = false;
      console.error("Failed to load trip", e);
      setMessages([
        {
          id: uid(),
          role: "assistant",
          content: "Couldn't load this conversation. Try again.",
        },
      ]);
    } finally {
      if (seq === loadSeq.current) setIsLoadingThread(false);
    }
  }, []);

  useEffect(() => {
    if (!threadId || isLoadingThread || !allowCacheWrite.current) return;
    threadCache.current.set(threadId, {
      messages,
      snapshot,
      selections,
      showPackageCard,
      activeTab,
      itinerarySubTab,
    });
  }, [
    threadId,
    isLoadingThread,
    messages,
    snapshot,
    selections,
    showPackageCard,
    activeTab,
    itinerarySubTab,
  ]);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;
    (async () => {
      let trips: SavedTripMetadata[] = [];
      try {
        const res = await listTrips();
        trips = res.trips || [];
        setSavedTrips(trips);
      } catch (e) {
        console.error("Failed to load saved trips", e);
      }
      const remembered = localStorage.getItem(THREAD_KEY);
      const known = trips.find((trip) => trip.thread_id === remembered);
      const id = known?.thread_id ?? trips[0]?.thread_id ?? remembered;
      if (!id) {
        try {
          const created = await createThread();
          localStorage.setItem(THREAD_KEY, created);
          setThreadId(created);
          setMessages([greeting()]);
        } catch (e) {
          console.error("Failed to start a trip", e);
        } finally {
          setIsLoadingThread(false);
        }
        return;
      }
      await loadThread(id);
    })();
  }, [loadThread]);

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
      refreshSavedTrips();
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
  }, [refreshSavedTrips]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!threadId || !content.trim() || isStreaming || isLoadingThread) return;
      allowCacheWrite.current = true;
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
    [threadId, isStreaming, isLoadingThread, handleEvent]
  );

  const updateSelections = useCallback(
    async (next: Selections) => {
      const capped = capSelections(next);
      setSelections(capped);
      if (snapshot?.itinerary) setAwaitingPlanUpdate(true);
      if (threadId) {
        await patchSelections(threadId, capped as Record<string, unknown>);
      }
    },
    [threadId, snapshot?.itinerary]
  );

  const confirmPlanUpdate = useCallback(() => {
    setAwaitingPlanUpdate(false);
    void sendMessage("Yes, update the itinerary around my current selections.");
  }, [sendMessage]);

  const keepPlan = useCallback(() => {
    setAwaitingPlanUpdate(false);
  }, []);

  const newTrip = useCallback(async () => {
    loadSeq.current += 1;
    allowCacheWrite.current = true;
    setIsLoadingThread(true);
    try {
      const id = await createThread();
      localStorage.setItem(THREAD_KEY, id);
      setThreadId(id);
      setSnapshot(null);
      setSteps([]);
      setSelections({});
      setAwaitingPlanUpdate(false);
      setShowPackageCard(false);
      setActiveTab("itinerary");
      setMessages([
        {
          id: uid(),
          role: "assistant",
          content: "Starting a fresh trip. Where would you like to go?",
        },
      ]);
      await refreshSavedTrips();
    } catch (e) {
      console.error("Failed to start a trip", e);
    } finally {
      setIsLoadingThread(false);
    }
  }, [refreshSavedTrips]);

  const switchTrip = useCallback(
    async (id: string) => {
      if (isStreaming) return;
      if (id === threadId && threadCache.current.has(id)) return;
      await loadThread(id);
    },
    [isStreaming, threadId, loadThread]
  );

  const removeTrip = useCallback(async (id: string) => {
    try {
      threadCache.current.delete(id);
      await deleteTrip(id);
      await refreshSavedTrips();
      if (threadId === id) {
        await newTrip();
      }
    } catch (e) {
      console.error("Failed to delete trip", e);
    }
  }, [threadId, newTrip, refreshSavedTrips]);

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
    awaitingPlanUpdate,
    confirmPlanUpdate,
    keepPlan,
    showPackageCard,
    isStreaming,
    isLoadingThread,
    sendMessage,
    newTrip,
    savedTrips,
    switchTrip,
    removeTrip,
    structured: snapshot?.structured as Record<string, unknown> | undefined,
    itinerary: snapshot?.itinerary as Itinerary | undefined,
    weather: snapshot?.weather as WeatherOutlook | undefined,
    destinationAbout: snapshot?.destination_about ?? "",
    flights: snapshot?.flights_data as FlightsData | undefined,
    trains: (snapshot?.trains ?? null) as TrainsData | null,
    hotels: (snapshot?.hotel_search_results ?? null) as HotelProperty[] | null,
  };
}
