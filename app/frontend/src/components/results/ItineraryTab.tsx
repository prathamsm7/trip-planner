"use client";

import type { Itinerary, WeatherOutlook } from "@/lib/types";

interface Props {
  subTab: "overview" | "daily";
  setSubTab: (t: "overview" | "daily") => void;
  itinerary?: Itinerary;
  weather?: WeatherOutlook;
  destinationAbout: string;
  structured?: Record<string, unknown>;
}

export function ItineraryTab({
  subTab,
  setSubTab,
  itinerary,
  weather,
  destinationAbout,
  structured,
}: Props) {
  const dest = (structured?.destinationLocation as string) ?? "your destination";
  const days = itinerary?.days?.length ?? 0;

  return (
    <div>
      <div className="flex gap-4 border-b mb-6">
        {(["overview", "daily"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setSubTab(t)}
            className={`pb-2 text-sm capitalize ${
              subTab === t
                ? "border-b-2 border-safar-navy font-medium text-safar-navy"
                : "text-gray-500"
            }`}
          >
            {t === "daily" ? "Daily Plan" : "Overview"}
          </button>
        ))}
      </div>

      {subTab === "overview" && (
        <div className="space-y-6">
          <section>
            <h3 className="font-semibold text-lg mb-2">About {dest}</h3>
            <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">
              {destinationAbout || itinerary?.summary || "No overview yet."}
            </p>
          </section>

          {itinerary && (
            <section className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: `${days} Days`, icon: "🗓️" },
                { label: "Itinerary", icon: "🗺️" },
                { label: (structured?.travel_style as string) ?? "Trip", icon: "👥" },
                { label: (structured?.budget as string) ?? "Budget", icon: "💰" },
              ].map((c) => (
                <div
                  key={c.label}
                  className="rounded-xl border bg-gray-50 p-4 text-center"
                >
                  <div className="text-2xl mb-1">{c.icon}</div>
                  <p className="text-sm font-medium capitalize">{c.label}</p>
                </div>
              ))}
            </section>
          )}

          {weather?.days && weather.days.length > 0 && (
            <section>
              <h3 className="font-semibold text-lg mb-3">Weather outlook</h3>
              <p className="text-sm text-gray-500 mb-3">{weather.summary}</p>
              {/* <div className="space-y-2">
                {weather.days.map((d, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between rounded-lg border px-4 py-3 text-sm"
                  >
                    <div>
                      <p className="font-medium">{d.day_label}</p>
                      <p className="text-gray-500">{d.condition}</p>
                    </div>
                    <div className="text-right text-gray-600">
                      <p>{d.temp_range}</p>
                      <p className="text-xs">
                        {d.humidity} · {d.wind}
                      </p>
                    </div>
                  </div>
                ))}
              </div> */}
            </section>
          )}
        </div>
      )}

      {subTab === "daily" && (
        <div className="space-y-6">
          {itinerary?.summary && (
            <p className="text-sm text-gray-600 border-l-4 border-safar-red pl-4">
              {itinerary.summary}
            </p>
          )}
          {itinerary?.days?.map((day) => (
            <div key={day.day} className="border rounded-xl overflow-hidden">
              <div className="bg-safar-navy text-white px-4 py-2 text-sm font-semibold">
                Day {day.day} — {day.location}
              </div>
              {day.plan.map((slot, i) => (
                <div key={i} className="px-4 py-3 border-t text-sm space-y-2">
                  {(["morning", "afternoon", "evening"] as const).map((period) => {
                    const items = slot[period];
                    if (!items?.length) return null;
                    return (
                      <div key={period}>
                        <p className="font-medium capitalize text-gray-800">{period}</p>
                        <ul className="list-disc list-inside text-gray-600">
                          {items.map((item, j) => (
                            <li key={j}>{item}</li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          ))}
          {!itinerary?.days?.length && (
            <p className="text-gray-500 text-sm">No daily plan yet.</p>
          )}
        </div>
      )}
    </div>
  );
}
