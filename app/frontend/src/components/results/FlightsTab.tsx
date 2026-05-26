"use client";

import type { FlightsData, FlightOption, Selections } from "@/lib/types";

interface Props {
  flights?: FlightsData;
  source: string;
  dest: string;
  selections: Selections;
  onSelections: (s: Selections) => void;
}

export function FlightsTab({ flights, source, dest, selections, onSelections }: Props) {
  const list = [...(flights?.best_flights ?? []), ...(flights?.other_flights ?? [])];
  const depCode = flights?.airport_meta?.departure_airport_code ?? source.slice(0, 3).toUpperCase();
  const arrCode = flights?.airport_meta?.arrival_airport_code ?? dest.slice(0, 3).toUpperCase();

  const hasSearched = flights != null && "best_flights" in flights;

  if (!list.length) {
    if (!hasSearched) {
      return (
        <p className="text-sm text-gray-500">
          No flight search yet. Ask me to search for flights when you&apos;re ready.
        </p>
      );
    }

    const alternatives = (flights as Record<string, unknown> | undefined)?.alternatives as
      | { nearby_airports?: { name: string; code: string; location: string }[]; railway_stations?: { name: string; code: string; location: string }[]; suggestions?: string[] }
      | undefined;

    if (alternatives?.suggestions?.length) {
      return (
        <div className="space-y-4">
          <p className="text-sm font-medium text-gray-700">
            No direct flights found to {dest}
          </p>
          <p className="text-sm text-gray-500">Here are some alternatives:</p>
          <ul className="space-y-2">
            {alternatives.suggestions.map((s, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                <span className="text-safar-red mt-0.5">•</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
          {alternatives.nearby_airports && alternatives.nearby_airports.length > 0 && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <p className="text-xs font-medium text-blue-700 mb-2">Nearby airports</p>
              <div className="flex flex-wrap gap-2">
                {alternatives.nearby_airports.map((ap) => (
                  <span key={ap.code} className="text-xs bg-white px-2 py-1 rounded border border-blue-200">
                    {ap.name} ({ap.code})
                  </span>
                ))}
              </div>
            </div>
          )}
          {alternatives.railway_stations && alternatives.railway_stations.length > 0 && (
            <div className="mt-2 p-3 bg-green-50 rounded-lg">
              <p className="text-xs font-medium text-green-700 mb-2">Nearest railway stations</p>
              <div className="flex flex-wrap gap-2">
                {alternatives.railway_stations.map((rs) => (
                  <span key={rs.code} className="text-xs bg-white px-2 py-1 rounded border border-green-200">
                    {rs.name} ({rs.code})
                  </span>
                ))}
              </div>
            </div>
          )}
          <p className="text-xs text-gray-400 mt-2">
            Ask me to search flights to a nearby airport instead.
          </p>
        </div>
      );
    }

    return (
      <p className="text-sm text-gray-500">
        No flights found for this route. Check the suggestions in chat.
      </p>
    );
  }

  const cheapest = list.reduce((min, f, i) => {
    const p = f.price ?? Infinity;
    return p < (list[min]?.price ?? Infinity) ? i : min;
  }, 0);
  const fastest = list.reduce((min, f, i) => {
    const d = f.total_duration ?? Infinity;
    return d < (list[min]?.total_duration ?? Infinity) ? i : min;
  }, 0);

  return (
    <div>
      <p className="text-sm font-medium text-gray-700 mb-4">Round trip selection</p>
      <div className="grid grid-cols-2 gap-3 mb-6">
        <LegBox
          label={`${depCode} → ${arrCode}`}
          selected={selections.outboundFlightIndex != null}
        />
        <LegBox
          label={`${arrCode} → ${depCode}`}
          selected={selections.returnFlightIndex != null}
        />
      </div>

      <div className="space-y-3">
        {list.map((flight, index) => (
          <FlightCard
            key={index}
            flight={flight}
            index={index}
            badges={[
              index === cheapest ? "Cheapest" : null,
              index === fastest ? "Fastest" : null,
            ].filter(Boolean) as string[]}
            selected={
              selections.outboundFlightIndex === index ||
              selections.returnFlightIndex === index
            }
            onSelect={() => {
              const next = { ...selections };
              if (next.outboundFlightIndex == null) {
                next.outboundFlightIndex = index;
              } else if (next.returnFlightIndex == null && next.outboundFlightIndex !== index) {
                next.returnFlightIndex = index;
              } else {
                next.outboundFlightIndex = index;
                next.returnFlightIndex = null;
              }
              onSelections(next);
            }}
          />
        ))}
      </div>
    </div>
  );
}

function LegBox({ label, selected }: { label: string; selected: boolean }) {
  return (
    <div
      className={`rounded-lg border-2 border-dashed p-4 text-center text-sm ${
        selected ? "border-green-500 bg-green-50" : "border-gray-300"
      }`}
    >
      <p className="font-medium">{label}</p>
      <p className="text-xs text-gray-500 mt-1">
        {selected ? "Flight selected" : "Please select a flight for this leg"}
      </p>
    </div>
  );
}

function FlightCard({
  flight,
  index,
  badges,
  selected,
  onSelect,
}: {
  flight: FlightOption;
  index: number;
  badges: string[];
  selected: boolean;
  onSelect: () => void;
}) {
  const leg = flight.flights?.[0];
  const dep = leg?.departure_airport;
  const arr = leg?.arrival_airport;

  return (
    <div
      className={`border rounded-xl p-4 ${selected ? "ring-2 ring-safar-navy" : ""}`}
    >
      <div className="flex justify-between items-start gap-4">
        <div className="flex-1">
          <div className="flex gap-2 mb-2">
            {badges.map((b) => (
              <span
                key={b}
                className="text-xs bg-safar-red/10 text-safar-red px-2 py-0.5 rounded"
              >
                {b}
              </span>
            ))}
          </div>
          <p className="font-semibold text-sm">
            {leg?.airline} {leg?.flight_number}
          </p>
          <div className="flex items-center gap-4 mt-2 text-sm">
            <div>
              <p className="font-medium">{dep?.time?.slice(11, 16) ?? "—"}</p>
              <p className="text-gray-500 text-xs">{dep?.id}</p>
            </div>
            <span className="text-gray-400">
              {flight.total_duration ? `${flight.total_duration} min` : "—"}
            </span>
            <div>
              <p className="font-medium">{arr?.time?.slice(11, 16) ?? "—"}</p>
              <p className="text-gray-500 text-xs">{arr?.id}</p>
            </div>
          </div>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold">
            ₹{flight.price?.toLocaleString("en-IN") ?? "—"}
          </p>
          <p className="text-xs text-gray-500">{flight.type ?? "Round trip"}</p>
          <button
            type="button"
            onClick={onSelect}
            className={`mt-2 px-4 py-1.5 rounded text-sm font-medium ${
              selected
                ? "bg-green-600 text-white"
                : "bg-safar-red text-white hover:bg-red-700"
            }`}
          >
            {selected ? "Selected" : "Select"}
          </button>
        </div>
      </div>
    </div>
  );
}
