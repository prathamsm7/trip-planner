"use client";

import type { HotelProperty, Selections } from "@/lib/types";

interface Props {
  hotels: HotelProperty[] | null;
  selections: Selections;
  onSelections: (s: Selections) => void;
}

export function HotelsTab({ hotels, selections, onSelections }: Props) {
  if (hotels === null) {
    return (
      <p className="text-sm text-gray-500">
        No hotel search yet. Ask me to search for hotels when you&apos;re ready.
      </p>
    );
  }

  if (!hotels.length) {
    return (
      <div className="space-y-3">
        <p className="text-sm font-medium text-gray-700">No accommodation found</p>
        <p className="text-sm text-gray-500">
          We couldn&apos;t find matching stays for your dates and filters. Try these:
        </p>
        <ul className="space-y-2">
          <li className="flex items-start gap-2 text-sm text-gray-600">
            <span className="text-safar-red mt-0.5">•</span>
            <span>Ask me to search for a different type — hotel, guesthouse, airbnb, or homestay.</span>
          </li>
          <li className="flex items-start gap-2 text-sm text-gray-600">
            <span className="text-safar-red mt-0.5">•</span>
            <span>Adjust your travel dates — availability varies by season.</span>
          </li>
          <li className="flex items-start gap-2 text-sm text-gray-600">
            <span className="text-safar-red mt-0.5">•</span>
            <span>Try searching for stays in a nearby town.</span>
          </li>
        </ul>
        <p className="text-xs text-gray-400 mt-2">
          Just tell me what you&apos;d like to change in chat.
        </p>
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm text-gray-600 mb-4">Showing {hotels.length} hotels</p>
      <div className="grid gap-4 sm:grid-cols-2">
        {hotels.map((hotel, index) => {
          const selected = selections.hotelIndices?.includes(index);
          const price =
            hotel.rate_per_night?.extracted_lowest ??
            hotel.rate_per_night?.lowest;
          const thumb = hotel.images?.[0]?.thumbnail;

          return (
            <div
              key={index}
              className={`border rounded-xl overflow-hidden ${selected ? "ring-2 ring-safar-navy" : ""}`}
            >
              {thumb && (
                <img
                  src={thumb}
                  alt=""
                  className="w-full h-40 object-cover bg-gray-100"
                />
              )}
              <div className="p-4">
                <p className="font-semibold text-sm line-clamp-2">{hotel.name}</p>
                <p className="text-xs text-gray-500 mt-1">
                  ★ {hotel.overall_rating ?? "—"} · {hotel.reviews ?? 0} reviews
                </p>
                {hotel.amenities && hotel.amenities.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {hotel.amenities.slice(0, 3).map((a) => (
                      <span
                        key={a}
                        className="text-xs bg-gray-100 px-2 py-0.5 rounded"
                      >
                        {a}
                      </span>
                    ))}
                  </div>
                )}
                <p className="text-lg font-bold mt-3">
                  {typeof price === "number"
                    ? `₹${price.toLocaleString("en-IN")}`
                    : price ?? "—"}
                  <span className="text-xs font-normal text-gray-500"> / night</span>
                </p>
                <div className="flex gap-2 mt-3">
                  <button
                    type="button"
                    onClick={() => {
                      const indices = new Set(selections.hotelIndices ?? []);
                      if (selected) indices.delete(index);
                      else indices.add(index);
                      onSelections({
                        ...selections,
                        hotelIndices: Array.from(indices),
                      });
                    }}
                    className={`flex-1 py-2 rounded text-sm font-medium border ${
                      selected
                        ? "bg-safar-navy text-white border-safar-navy"
                        : "border-gray-300 hover:bg-gray-50"
                    }`}
                  >
                    {selected ? "Added" : "Add to Trip"}
                  </button>
                  <button
                    type="button"
                    className="flex-1 py-2 rounded text-sm font-medium bg-safar-red text-white"
                    onClick={() => {
                      onSelections({
                        ...selections,
                        hotelIndices: [index],
                      });
                    }}
                  >
                    Choose Room
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
