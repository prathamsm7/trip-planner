"use client";

import { cappedHotelIndices } from "@/lib/selectionCaps";
import type { FlightsData, HotelProperty, Itinerary, Selections, TrainOption, TrainsData } from "@/lib/types";

interface Props {
  itinerary?: Itinerary;
  flights?: FlightsData;
  trains?: TrainsData | null;
  hotels: HotelProperty[] | null;
  selections: Selections;
  structured?: Record<string, unknown>;
}

function nightsBetween(start?: string, end?: string) {
  if (!start || !end) return 0;
  const from = Date.parse(`${start.slice(0, 10)}T00:00:00`);
  const to = Date.parse(`${end.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(from) || Number.isNaN(to) || to <= from) return 0;
  return Math.round((to - from) / 86_400_000);
}

function rupees(amount: number) {
  return `₹${amount.toLocaleString("en-IN")}`;
}

function lowestFare(train?: TrainOption | null) {
  const fares = (train?.availability ?? [])
    .map((row) => ({ fare: Number(row.fare), label: row.class_label || row.class_code }))
    .filter((row) => Number.isFinite(row.fare));
  if (!fares.length) return null;
  return fares.reduce((best, row) => (row.fare < best.fare ? row : best));
}

function trainLabel(train: TrainOption) {
  const fare = lowestFare(train);
  const name = `${train.train_name || "Train"} ${train.train_number}`.trim();
  if (!fare) return name;
  const klass = fare.label ? `${fare.label} · ` : "";
  return `${name} · ${klass}${rupees(fare.fare)}`;
}

function nightlyRate(hotel: HotelProperty) {
  const rate = hotel.rate_per_night?.extracted_lowest;
  return typeof rate === "number" && Number.isFinite(rate) ? rate : null;
}

export function PackageTab({
  itinerary,
  flights,
  trains,
  hotels,
  selections,
  structured,
}: Props) {
  const outboundList = [
    ...(flights?.outbound?.best_flights ?? []),
    ...(flights?.outbound?.other_flights ?? []),
  ];
  const returnList = [
    ...(flights?.return_flights?.best_flights ?? []),
    ...(flights?.return_flights?.other_flights ?? []),
  ];
  const outFlight =
    selections.outboundFlightIndex != null ? outboundList[selections.outboundFlightIndex] : null;
  const retFlight =
    selections.returnFlightIndex != null ? returnList[selections.returnFlightIndex] : null;
  const outTrain =
    selections.outboundTrainIndex != null ? trains?.outbound?.[selections.outboundTrainIndex] : null;
  const retTrain =
    selections.returnTrainIndex != null ? trains?.return?.[selections.returnTrainIndex] : null;
  const hotelList = cappedHotelIndices(selections.hotelIndices)
    .map((i) => (hotels ?? [])[i])
    .filter(Boolean);

  const dates = structured?.date_range as { start?: string; end?: string } | undefined;
  const nights = nightsBetween(dates?.start, dates?.end);
  const flightTotal = (outFlight?.price ?? 0) + (retFlight?.price ?? 0);
  const trainTotal = (lowestFare(outTrain)?.fare ?? 0) + (lowestFare(retTrain)?.fare ?? 0);
  const hotelTotal = hotelList.reduce((sum, hotel) => {
    const rate = nightlyRate(hotel);
    return rate != null && nights > 0 ? sum + rate * nights : sum;
  }, 0);
  const packageTotal = flightTotal + trainTotal + hotelTotal;

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
          value={dates?.start && dates?.end ? `${dates.start} → ${dates.end}` : "—"}
        />
        <Row label="Travelers" value={String(structured?.number_of_people ?? "—")} />
        <Row
          label="Outbound flight"
          value={
            outFlight
              ? `${outFlight.flights?.[0]?.airline ?? "Flight"} · ${rupees(outFlight.price ?? 0)}`
              : "None"
          }
        />
        <Row
          label="Return flight"
          value={
            retFlight
              ? `${retFlight.flights?.[0]?.airline ?? "Flight"} · ${rupees(retFlight.price ?? 0)}`
              : "None"
          }
        />
        <Row label="Outbound train" value={outTrain ? trainLabel(outTrain) : "None"} />
        <Row label="Return train" value={retTrain ? trainLabel(retTrain) : "None"} />
        {hotelList.length === 0 && <Row label="Hotels" value="None" />}
        {hotelList.map((hotel, index) => (
          <Row key={`${hotel.name}-${index}`} label="Hotel" value={hotelStayLabel(hotel, nights)} />
        ))}
        {packageTotal > 0 && (
          <p className="font-bold text-lg pt-2 border-t">Est. total: {rupees(packageTotal)}</p>
        )}
      </section>
    </div>
  );
}

function hotelStayLabel(hotel: HotelProperty, nights: number) {
  const name = hotel.name || "Hotel";
  const rate = nightlyRate(hotel);
  if (rate == null) return `${name} · nightly rate unavailable`;
  if (nights <= 0) return `${name} · ${rupees(rate)} / night`;
  return `${name} · ${rupees(rate)} × ${nights} nights = ${rupees(rate * nights)}`;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-gray-500">{label}</span>
      <span className="font-medium text-right">{value}</span>
    </div>
  );
}
