"use client";

import type {
  FlightsData,
  HotelProperty,
  Itinerary,
  Selections,
  TabId,
  TrainsData,
  WeatherOutlook,
} from "@/lib/types";
import { FlightsTab } from "./FlightsTab";
import { HotelsTab } from "./HotelsTab";
import { ItineraryTab } from "./ItineraryTab";
import { PackageTab } from "./PackageTab";
import { TrainsTab } from "./TrainsTab";

interface Props {
  activeTab: TabId;
  setActiveTab: (t: TabId) => void;
  itinerarySubTab: "overview" | "daily";
  setItinerarySubTab: (t: "overview" | "daily") => void;
  structured?: Record<string, unknown>;
  itinerary?: Itinerary;
  weather?: WeatherOutlook;
  destinationAbout: string;
  flights?: FlightsData;
  trains?: TrainsData | null;
  hotels: HotelProperty[] | null;
  selections: Selections;
  onSelections: (s: Selections) => void;
  awaitingPlanUpdate?: boolean;
  onConfirmPlanUpdate?: () => void;
  onKeepPlan?: () => void;
}

export function ResultsPanel({
  activeTab,
  setActiveTab,
  itinerarySubTab,
  setItinerarySubTab,
  structured,
  itinerary,
  weather,
  destinationAbout,
  flights,
  trains,
  hotels,
  selections,
  onSelections,
  awaitingPlanUpdate,
  onConfirmPlanUpdate,
  onKeepPlan,
}: Props) {
  const dest = (structured?.destinationLocation as string) ?? "Destination";
  const source = (structured?.sourceLocation as string) ?? "";
  const dr = structured?.date_range as { start?: string; end?: string } | undefined;
  const tabs: { id: TabId; label: string }[] = [
    { id: "itinerary", label: "Itinerary" },
    { id: "flights", label: "Flight" },
    { id: "trains", label: "Train" },
    { id: "hotels", label: "Hotels" },
    { id: "package", label: "Packages" },
  ];

  const hasFlightOptions =
    (flights?.outbound?.best_flights?.length ?? 0) > 0 ||
    (flights?.outbound?.other_flights?.length ?? 0) > 0 ||
    (flights?.return_flights?.best_flights?.length ?? 0) > 0 ||
    (flights?.return_flights?.other_flights?.length ?? 0) > 0;
  const hasTrains = (trains?.outbound?.length ?? 0) > 0 || (trains?.return?.length ?? 0) > 0 || Boolean(trains?.origin_station);
  const hasContent = Boolean(dest && dest !== "Destination") || itinerary || hasFlightOptions || hasTrains || (hotels && hotels.length);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-white">
      <div className="shrink-0 px-6 py-4 border-b">
        <h2 className="text-lg font-semibold text-gray-900">Search results</h2>
        {dr?.start && dr?.end && (
          <p className="text-sm text-gray-500 mt-0.5">
            {dest} · {formatDate(dr.start)} – {formatDate(dr.end)}
          </p>
        )}
      </div>

      {hasContent ? (
        <>
          <div className="shrink-0 flex gap-1 px-4 pt-3 border-b overflow-x-auto">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setActiveTab(t.id)}
                className={`px-4 py-2 text-sm whitespace-nowrap border-b-2 -mb-px ${
                  activeTab === t.id
                    ? "border-safar-navy text-safar-navy font-medium"
                    : "border-transparent text-gray-500 hover:text-gray-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-6">
            {awaitingPlanUpdate && itinerary && (
              <div className="mb-5 rounded-lg border border-amber-200 bg-amber-50 p-4">
                <p className="text-sm text-gray-800">
                  Update the day plan around your selected flights, trains, and hotels?
                </p>
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    onClick={onConfirmPlanUpdate}
                    className="rounded-md bg-safar-navy px-3 py-1.5 text-sm text-white"
                  >
                    Update plan
                  </button>
                  <button
                    type="button"
                    onClick={onKeepPlan}
                    className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700"
                  >
                    Keep this plan
                  </button>
                </div>
              </div>
            )}
            {activeTab === "itinerary" && (
              <ItineraryTab
                subTab={itinerarySubTab}
                setSubTab={setItinerarySubTab}
                itinerary={itinerary}
                weather={weather}
                destinationAbout={destinationAbout}
                structured={structured}
              />
            )}
            {activeTab === "flights" && (
              <FlightsTab
                flights={flights}
                source={source}
                dest={dest}
                selections={selections}
                onSelections={onSelections}
              />
            )}
            {activeTab === "trains" && (
              <TrainsTab
                trains={trains}
                source={source}
                dest={dest}
                selections={selections}
                onSelections={onSelections}
              />
            )}
            {activeTab === "hotels" && (
              <HotelsTab hotels={hotels} selections={selections} onSelections={onSelections} />
            )}
            {activeTab === "package" && (
              <PackageTab
                itinerary={itinerary}
                flights={flights}
                trains={trains}
                hotels={hotels}
                selections={selections}
                structured={structured}
              />
            )}
          </div>
        </>
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain flex items-center justify-center text-gray-400 text-sm p-8 text-center">
          Plan a trip in the chat to see itinerary, flights, and hotels here.
        </div>
      )}
    </div>
  );
}

function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return iso;
  }
}
