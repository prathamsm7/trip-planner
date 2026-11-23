import type { Selections } from "@/lib/types";

/** One flight and one train per direction. Hotels can be compared, up to this many. */
export const HOTEL_SELECTION_CAP = 3;

export function cappedHotelIndices(indices?: number[] | null) {
  const chosen: number[] = [];
  for (const index of indices ?? []) {
    if (!Number.isInteger(index) || chosen.includes(index)) continue;
    chosen.push(index);
    if (chosen.length === HOTEL_SELECTION_CAP) break;
  }
  return chosen;
}

export function capSelections(selections: Selections): Selections {
  return {
    ...selections,
    hotelIndices: cappedHotelIndices(selections.hotelIndices),
  };
}
