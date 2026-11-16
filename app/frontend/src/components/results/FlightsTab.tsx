"use client";

import type { FlightsData, FlightOption, FlightLegBundle, Selections } from "@/lib/types";

interface Props {
  flights?: FlightsData;
  source: string;
  dest: string;
  selections: Selections;
  onSelections: (s: Selections) => void;
}

function legList(leg?: FlightLegBundle | null) {
  return [...(leg?.best_flights ?? []), ...(leg?.other_flights ?? [])];
}

export function FlightsTab({ flights, source, dest, selections, onSelections }: Props) {
  const depCode = flights?.airport_meta?.departure_airport_code ?? source.slice(0, 3).toUpperCase();
  const arrCode = flights?.airport_meta?.arrival_airport_code ?? dest.slice(0, 3).toUpperCase();

  const outboundList = legList(flights?.outbound);
  const returnList = legList(flights?.return_flights);

  const hasSearched =
    flights != null && ("outbound" in flights || "return_flights" in flights);

  if (!outboundList.length && !returnList.length) {
    if (!hasSearched) {
      return (
        <p className="text-sm text-gray-500">
          No flight search yet. Ask me to search for flights when you&apos;re ready.
        </p>
      );
    }

    const alternatives = (flights as Record<string, unknown> | undefined)?.alternatives as
      | {
          nearby_airports?: { name: string; code: string; location: string }[];
          railway_stations?: { name: string; code: string; location: string }[];
          suggestions?: string[];
        }
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
                  <span
                    key={ap.code}
                    className="text-xs bg-white px-2 py-1 rounded border border-blue-200"
                  >
                    {ap.name} ({ap.code})
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

  return (
    <div className="space-y-8">
      <LegSection
        title={`Outbound · ${depCode} → ${arrCode}${legDateLabel(outboundList) ? ` · ${legDateLabel(outboundList)}` : ""}`}
        emptyText="No outbound flights found for these dates."
        list={outboundList}
        selectedIndex={selections.outboundFlightIndex ?? null}
        onSelect={(index) =>
          onSelections({ ...selections, outboundFlightIndex: index })
        }
      />
      <LegSection
        title={`Return · ${arrCode} → ${depCode}${legDateLabel(returnList) ? ` · ${legDateLabel(returnList)}` : ""}`}
        emptyText="No return flights found for these dates."
        list={returnList}
        selectedIndex={selections.returnFlightIndex ?? null}
        onSelect={(index) =>
          onSelections({ ...selections, returnFlightIndex: index })
        }
      />
    </div>
  );
}

function splitStamp(time?: string): { date: string; clock: string } {
  if (!time) return { date: "", clock: "—" };
  const match = time.match(/(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (!match) return { date: "", clock: time.slice(0, 5) || "—" };
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const day = String(Number(match[3]));
  const month = months[Number(match[2]) - 1] ?? match[2];
  return { date: `${day} ${month}`, clock: `${match[4]}:${match[5]}` };
}

function legDateLabel(list: FlightOption[]): string {
  const dates = new Set(
    list
      .map((flight) => splitStamp(flight.flights?.[0]?.departure_airport?.time).date)
      .filter(Boolean),
  );
  if (dates.size === 1) return [...dates][0];
  return "";
}

function LegSection({
  title,
  emptyText,
  list,
  selectedIndex,
  onSelect,
}: {
  title: string;
  emptyText: string;
  list: FlightOption[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}) {
  if (!list.length) {
    return (
      <section>
        <h3 className="text-sm font-semibold text-gray-800 mb-2">{title}</h3>
        <p className="text-sm text-gray-500">{emptyText}</p>
      </section>
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
    <section>
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        <p className="text-xs text-gray-500">
          {selectedIndex != null ? "Flight selected" : "Select one option"}
        </p>
      </div>
      <div className="space-y-3">
        {list.map((flight, index) => (
          <FlightCard
            key={`${title}-${index}`}
            flight={flight}
            badges={[
              index === cheapest ? "Cheapest" : null,
              index === fastest ? "Fastest" : null,
            ].filter(Boolean) as string[]}
            selected={selectedIndex === index}
            onSelect={() => onSelect(index)}
          />
        ))}
      </div>
    </section>
  );
}

function FlightCard({
  flight,
  badges,
  selected,
  onSelect,
}: {
  flight: FlightOption;
  badges: string[];
  selected: boolean;
  onSelect: () => void;
}) {
  const leg = flight.flights?.[0];
  const dep = leg?.departure_airport;
  const last = flight.flights?.[flight.flights.length - 1];
  const finalArr = last?.arrival_airport ?? leg?.arrival_airport;
  const departs = splitStamp(dep?.time);
  const arrives = splitStamp(finalArr?.time);

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
            {(flight.flights?.length ?? 0) > 1
              ? ` · ${(flight.flights?.length ?? 1) - 1} stop`
              : " · Non-stop"}
          </p>
          <div className="flex items-center gap-4 mt-2 text-sm">
            <div>
              <p className="font-medium">{departs.clock}</p>
              {departs.date ? <p className="text-gray-500 text-xs">{departs.date}</p> : null}
              <p className="text-gray-500 text-xs">{dep?.id}</p>
            </div>
            <span className="text-gray-400">
              {flight.total_duration ? `${flight.total_duration} min` : "—"}
            </span>
            <div>
              <p className="font-medium">{arrives.clock}</p>
              {arrives.date ? <p className="text-gray-500 text-xs">{arrives.date}</p> : null}
              <p className="text-gray-500 text-xs">{finalArr?.id}</p>
            </div>
          </div>
        </div>
        <div className="text-right">
          <p className="text-lg font-bold">
            ₹{flight.price?.toLocaleString("en-IN") ?? "—"}
          </p>
          <p className="text-xs text-gray-500">{flight.type ?? "One way"}</p>
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
