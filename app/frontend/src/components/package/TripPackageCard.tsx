"use client";

import { useState } from "react";

interface Props {
  destination: string;
  source: string;
  dateStart?: string;
  dateEnd?: string;
  onSelect: (tab: "itinerary" | "flights" | "hotels" | "package") => void;
}

const rows = [
  {
    key: "itinerary" as const,
    icon: "📍",
    title: (d: string) => `${d.toUpperCase()} ITINERARY`,
    sub: "View trip details",
  },
  {
    key: "flights" as const,
    icon: "✈️",
    title: (d: string, s: string) => `${s || "—"} → ${d || "—"}`,
    sub: "Click to view flight options",
  },
  {
    key: "hotels" as const,
    icon: "🏨",
    title: () => "HOTELS",
    sub: "View available stays",
  },
  {
    key: "package" as const,
    icon: "🎁",
    title: () => "RECOMMENDED PACKAGE",
    sub: "View package details",
  },
];

export function TripPackageCard({ destination, source, onSelect }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-gray-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-50"
        aria-expanded={open}
      >
        <span className="text-xs font-semibold text-gray-700">Your Trip Package</span>
        <span className="text-gray-400 text-sm" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && (
        <div className="border-t border-gray-100 max-h-48 overflow-y-auto">
          <p className="px-4 py-1.5 text-[11px] text-gray-500 bg-gray-50">
            Tap a component to view details
          </p>
          {rows.map((row) => (
            <button
              key={row.key}
              type="button"
              onClick={() => onSelect(row.key)}
              className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 border-b border-gray-100 last:border-b-0 text-left"
            >
              <span className="text-lg">{row.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm text-gray-900 truncate">
                  {row.key === "itinerary"
                    ? row.title(destination)
                    : row.key === "flights"
                      ? row.title(destination, source)
                      : row.title()}
                </p>
                <p className="text-xs text-gray-500">{row.sub}</p>
              </div>
              <span className="text-gray-400">›</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
