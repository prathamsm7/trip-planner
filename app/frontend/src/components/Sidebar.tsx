"use client";

import { SavedTripMetadata } from "@/lib/api";

interface SidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  savedTrips: SavedTripMetadata[];
  activeThreadId: string | null;
  onSelectTrip: (threadId: string) => void;
  onDeleteTrip: (threadId: string) => void;
  onNewTrip: () => void;
}

export function Sidebar({
  isOpen,
  onToggle,
  savedTrips,
  activeThreadId,
  onSelectTrip,
  onDeleteTrip,
  onNewTrip,
}: SidebarProps) {
  const formatDateRange = (start: string, end: string) => {
    if (!start) return "";
    try {
      const s = new Date(start);
      const e = end ? new Date(end) : null;
      if (!e || start === end) {
        return s.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });
      }
      const sStr = s.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      const eStr = e.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
      return `${sStr} - ${eStr}`;
    } catch {
      return `${start} - ${end}`;
    }
  };

  const getTripLabel = (trip: SavedTripMetadata) => {
    const origin = trip.origin?.trim();
    const destination = trip.destination?.trim();
    if (origin && destination) {
      return `${origin} → ${destination}`;
    }
    if (destination) {
      return `Trip to ${destination}`;
    }
    return "New Trip Planner";
  };

  return (
    <aside
      className={`shrink-0 h-full border-r bg-[#1a2744] text-white flex flex-col transition-all duration-300 ${
        isOpen ? "w-[280px]" : "w-0 overflow-hidden border-r-0"
      }`}
    >
      <div className="p-4 border-b border-white/10 flex items-center justify-between shrink-0">
        <h2 className="font-semibold text-lg tracking-tight text-white/90">Your Trips</h2>
        <button
          type="button"
          onClick={onToggle}
          className="p-1 hover:bg-white/10 rounded transition-colors text-white/70 hover:text-white lg:hidden"
          title="Close sidebar"
          aria-label="Close sidebar"
        >
          ✕
        </button>
      </div>

      <div className="p-3 shrink-0">
        <button
          type="button"
          onClick={onNewTrip}
          className="w-full flex items-center justify-center gap-2 py-2 px-3 border border-white/20 hover:border-white/40 bg-white/5 hover:bg-white/10 rounded-lg text-sm font-medium transition-all text-white/90 hover:text-white"
        >
          <span>＋</span> Plan New Trip
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-1 p-3">
        {savedTrips.length === 0 ? (
          <div className="text-center py-8 px-4">
            <p className="text-sm text-white/40">No trips planned yet.</p>
            <p className="text-xs text-white/30 mt-1">Start chatting to design your first trip package!</p>
          </div>
        ) : (
          savedTrips.map((trip) => {
            const isActive = trip.thread_id === activeThreadId;
            const label = getTripLabel(trip);
            const dates = formatDateRange(trip.start_date, trip.end_date);

            return (
              <div
                key={trip.thread_id}
                className={`group flex items-center justify-between rounded-lg transition-all text-left ${
                  isActive
                    ? "bg-white/10 text-white font-medium shadow-sm border border-white/10"
                    : "text-white/70 hover:text-white hover:bg-white/5"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSelectTrip(trip.thread_id)}
                  className="flex-1 min-w-0 p-3 block outline-none"
                >
                  <p className="text-sm truncate pr-2 font-medium">{label}</p>
                  {dates && <p className="text-[11px] text-white/40 mt-0.5">{dates}</p>}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteTrip(trip.thread_id);
                  }}
                  className="p-2 opacity-0 group-hover:opacity-100 hover:bg-white/10 rounded-md transition-all mr-2 text-white/40 hover:text-safar-red shrink-0"
                  title="Delete trip"
                  aria-label={`Delete trip to ${trip.destination || "destination"}`}
                >
                  🗑️
                </button>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
