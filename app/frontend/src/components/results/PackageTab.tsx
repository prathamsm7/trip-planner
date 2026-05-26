"use client";

import type { FlightsData, HotelProperty, Itinerary, Selections } from "@/lib/types";

interface Props {
  itinerary?: Itinerary;
  flights?: FlightsData;
  hotels: HotelProperty[] | null;
  selections: Selections;
  structured?: Record<string, unknown>;
}

export function PackageTab({
  itinerary,
  flights,
  hotels,
  selections,
  structured,
}: Props) {
  const list = [...(flights?.best_flights ?? []), ...(flights?.other_flights ?? [])];
  const out = selections.outboundFlightIndex != null ? list[selections.outboundFlightIndex] : null;
  const ret = selections.returnFlightIndex != null ? list[selections.returnFlightIndex] : null;
  const hotelList = (selections.hotelIndices ?? [])
    .map((i) => (hotels ?? [])[i])
    .filter(Boolean);

  const flightTotal = (out?.price ?? 0) + (ret?.price ?? 0);

  return (
    <div className="space-y-6 max-w-lg">
      <h3 className="font-semibold text-lg">Your recommended package</h3>
      <p className="text-sm text-gray-600">
        {itinerary?.summary ?? "Plan a trip to see your package summary."}
      </p>

      <section className="border rounded-xl p-4 space-y-3 text-sm">
        <Row label="Destination" value={(structured?.destinationLocation as string) ?? "—"} />
        <Row
          label="Dates"
          value={
            structured?.date_range
              ? `${(structured.date_range as { start: string }).start} → ${(structured.date_range as { end: string }).end}`
              : "—"
          }
        />
        <Row label="Travelers" value={String(structured?.number_of_people ?? "—")} />
        <Row
          label="Flights selected"
          value={
            out
              ? `${out.flights?.[0]?.airline ?? "Flight"} · ₹${out.price?.toLocaleString("en-IN")}`
              : "None"
          }
        />
        <Row label="Hotels selected" value={String(hotelList.length)} />
        {flightTotal > 0 && (
          <p className="font-bold text-lg pt-2 border-t">
            Est. flights total: ₹{flightTotal.toLocaleString("en-IN")}
          </p>
        )}
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-right">{value}</span>
    </div>
  );
}
