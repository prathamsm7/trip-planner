"use client";

import type { Selections, TrainAvailability, TrainOption, TrainStation, TrainsData } from "@/lib/types";

interface Props {
  trains?: TrainsData | null;
  source: string;
  dest: string;
  selections: Selections;
  onSelections: (s: Selections) => void;
}

function durationLabel(minutes?: number | null) {
  if (minutes == null || Number.isNaN(minutes)) return "";
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest}m`;
  if (!rest) return `${hours}h`;
  return `${hours}h ${rest}m`;
}

function statusClass(status?: string) {
  const value = (status || "").toUpperCase();
  if (value.includes("AVAILABLE") && !value.includes("NOT")) return "bg-green-50 text-green-800 border-green-200";
  if (value.includes("WL") || value.includes("RAC") || value.includes("WAIT")) {
    return "bg-amber-50 text-amber-800 border-amber-200";
  }
  return "bg-gray-50 text-gray-600 border-gray-200";
}

function AvailabilityList({ rows }: { rows?: TrainAvailability[] }) {
  if (!rows?.length) {
    return <p className="text-xs text-gray-400">Availability not listed for this train.</p>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {rows.map((row) => (
        <div
          key={`${row.class_code}-${row.text}`}
          className={`rounded-lg border px-2.5 py-1.5 text-xs ${statusClass(row.status || row.text)}`}
        >
          <p className="font-semibold">{row.class_label || row.class_code}</p>
          <p>{row.text || row.status || "Unknown"}</p>
          {row.fare != null && <p>₹{Number(row.fare).toLocaleString("en-IN")}</p>}
        </div>
      ))}
    </div>
  );
}

function TrainCard({
  train,
  selected,
  onSelect,
}: {
  train: TrainOption;
  selected: boolean;
  onSelect: () => void;
}) {
  const typeLabel = train.train_type_label || train.train_type;
  return (
    <article className={`rounded-xl border p-4 space-y-3 ${selected ? "ring-2 ring-safar-navy" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold text-gray-900">
            {train.train_name || "Train"}{" "}
            <span className="text-gray-500 font-medium">{train.train_number}</span>
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {train.from_station_name || train.from_station_code} →{" "}
            {train.to_station_name || train.to_station_code}
          </p>
        </div>
        {typeLabel && (
          <span className="shrink-0 rounded-full bg-safar-navy/10 text-safar-navy px-2.5 py-1 text-xs font-medium">
            {typeLabel}
          </span>
        )}
      </div>
      <div className="flex items-center gap-4 text-sm">
        <p className="font-medium">{train.departure_time || "—"}</p>
        <p className="text-xs text-gray-400">{durationLabel(train.duration_minutes)}</p>
        <p className="font-medium">{train.arrival_time || "—"}</p>
      </div>
      {!!train.classes?.length && (
        <div>
          <p className="text-xs font-medium text-gray-500 mb-1">Classes</p>
          <div className="flex flex-wrap gap-1.5">
            {train.classes.map((item) => (
              <span key={item.code} className="rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
                {item.label} ({item.code})
              </span>
            ))}
          </div>
        </div>
      )}
      <div>
        <p className="text-xs font-medium text-gray-500 mb-1">Availability</p>
        <AvailabilityList rows={train.availability} />
      </div>
      <button
        type="button"
        onClick={onSelect}
        className={`px-4 py-1.5 rounded text-sm font-medium ${
          selected ? "bg-green-600 text-white" : "bg-safar-red text-white hover:bg-red-700"
        }`}
      >
        {selected ? "Selected" : "Select"}
      </button>
    </article>
  );
}

function StationChips({ title, stations }: { title: string; stations: TrainStation[] }) {
  if (!stations.length) return null;
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1.5">{title}</p>
      <div className="flex flex-wrap gap-2">
        {stations.map((station) => (
          <span
            key={`${station.side}-${station.code}`}
            className="rounded-md border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700"
          >
            {station.name} ({station.code})
          </span>
        ))}
      </div>
    </div>
  );
}

function StationChoices({ trains }: { trains: TrainsData }) {
  const originFallbacks = trains.station_meta?.origin_fallbacks ?? [];
  const destinationFallbacks = trains.station_meta?.destination_fallbacks ?? [];
  if (!originFallbacks.length && !destinationFallbacks.length) return null;
  return (
    <div className="rounded-lg bg-blue-50 p-3 space-y-3">
      <p className="text-xs font-medium text-blue-800">Other stations</p>
      <StationChips title="Departure" stations={originFallbacks} />
      <StationChips title="Arrival" stations={destinationFallbacks} />
      <p className="text-xs text-blue-700">Ask me to search one of these stations instead.</p>
    </div>
  );
}

function Leg({
  title,
  trains,
  selectedIndex,
  onSelect,
}: {
  title: string;
  trains: TrainOption[];
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}) {
  if (!trains.length) return null;
  return (
    <section className="space-y-3">
      <h3 className="font-semibold text-gray-900">{title}</h3>
      {trains.map((train, index) => (
        <TrainCard
          key={`${train.train_number}-${train.departure_time}`}
          train={train}
          selected={selectedIndex === index}
          onSelect={() => onSelect(index)}
        />
      ))}
    </section>
  );
}

export function TrainsTab({ trains, source, dest, selections, onSelections }: Props) {
  const outbound = trains?.outbound ?? [];
  const returning = trains?.return ?? [];
  const from = trains?.origin_station;
  const to = trains?.destination_station;
  if (!outbound.length && !returning.length && !from && !to) {
    return (
      <p className="text-sm text-gray-500">
        No trains yet. Ask me to search trains from {source || "your city"} to {dest || "the destination"}.
      </p>
    );
  }
  if (!trains?.searched) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-700">
          Stations found: {from?.name || source} ({from?.code}) → {to?.name || dest} ({to?.code})
        </p>
        {trains && <StationChoices trains={trains} />}
      </div>
    );
  }
  if (!outbound.length && !returning.length) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-gray-500">
          {from?.name || source} ({from?.code}) → {to?.name || dest} ({to?.code})
        </p>
        <p className="text-sm text-gray-700">No trains for this station pair.</p>
        {trains && <StationChoices trains={trains} />}
      </div>
    );
  }
  return (
    <div className="space-y-8">
      <p className="text-sm text-gray-500">
        {from?.name || source} ({from?.code}) → {to?.name || dest} ({to?.code}). Select one
        outbound train and one return train.
      </p>
      <StationChoices trains={trains ?? {}} />
      <Leg
        title={`Outbound${trains?.outbound_date ? ` · ${trains.outbound_date}` : ""}`}
        trains={outbound}
        selectedIndex={selections.outboundTrainIndex ?? null}
        onSelect={(index) => onSelections({ ...selections, outboundTrainIndex: index })}
      />
      <Leg
        title={`Return${trains?.return_date ? ` · ${trains.return_date}` : ""}`}
        trains={returning}
        selectedIndex={selections.returnTrainIndex ?? null}
        onSelect={(index) => onSelections({ ...selections, returnTrainIndex: index })}
      />
    </div>
  );
}
