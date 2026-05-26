export type TabId = "itinerary" | "flights" | "hotels" | "package";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  kind?: "text" | "package" | "interrupt" | "steps";
}

export interface StepEvent {
  node: string;
  label: string;
  status: "running" | "done" | "pending" | "error";
  description?: string;
  startedAt?: number;
  durationMs?: number;
}

export interface TripSnapshot {
  structured?: Record<string, unknown> | null;
  follow_up_answers?: Record<string, string>;
  weather?: WeatherOutlook | null;
  destination_about?: string;
  itinerary?: Itinerary | null;
  transport_results?: unknown;
  activities_results?: unknown;
  user_current_intent?: string;
  hotel_search_results?: HotelProperty[];
  flights_data?: FlightsData;
  selections?: Selections;
  messages?: { role: string; content: string }[];
}

export interface WeatherDay {
  day_label: string;
  date?: string;
  temp_range: string;
  humidity: string;
  wind: string;
  condition: string;
}

export interface WeatherOutlook {
  destination: string;
  summary: string;
  days: WeatherDay[];
}

export interface Itinerary {
  summary: string;
  days: {
    day: number;
    location: string;
    plan: { morning: string[]; afternoon: string[]; evening: string[] }[];
  }[];
}

export interface FlightsData {
  best_flights?: FlightOption[];
  other_flights?: FlightOption[];
  airports?: unknown[];
  airport_meta?: {
    departure_airport_code?: string;
    arrival_airport_code?: string;
  };
}

export interface FlightOption {
  price?: number;
  total_duration?: number;
  type?: string;
  airline_logo?: string;
  flights?: {
    departure_airport?: { id?: string; name?: string; time?: string };
    arrival_airport?: { id?: string; name?: string; time?: string };
    airline?: string;
    flight_number?: string;
    duration?: number;
  }[];
}

export interface HotelProperty {
  name?: string;
  link?: string;
  description?: string;
  rate_per_night?: { lowest?: string; extracted_lowest?: number };
  overall_rating?: number;
  reviews?: number;
  images?: { original_image?: string; thumbnail?: string }[];
  amenities?: string[];
  type?: string;
}

export interface Selections {
  outboundFlightIndex?: number | null;
  returnFlightIndex?: number | null;
  hotelIndices?: number[];
}

export interface StreamEvent {
  type: string;
  node?: string;
  label?: string;
  description?: string;
  payload?: Record<string, unknown>;
  ui_hints?: { open_tab?: TabId | null; show_package_card?: boolean };
  message?: string;
  content?: string;
  role?: string;
  questions?: string[];
  question?: string;
  index?: number;
  total?: number;
  snapshot?: TripSnapshot;
  thread_id?: string;
}
