export type TabId = "itinerary" | "flights" | "trains" | "hotels" | "package";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  kind?: "text" | "package" | "steps";
}

export interface StepEvent {
  node: string;
  step_id?: string;
  label: string;
  status: "running" | "done" | "pending" | "error";
  description?: string;
  startedAt?: number;
  durationMs?: number;
}

export interface TripSnapshot {
  structured?: Record<string, unknown> | null;
  weather?: WeatherOutlook | null;
  destination_about?: string;
  itinerary?: Itinerary | null;
  hotel_search_results?: HotelProperty[];
  flights_data?: FlightsData;
  trains?: TrainsData | null;
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

export interface FlightLegBundle {
  best_flights?: FlightOption[];
  other_flights?: FlightOption[];
  shortlist?: unknown[];
}

export interface TrainClass {
  code: string;
  label: string;
}

export interface TrainAvailability {
  class_code: string;
  class_label?: string;
  status?: string;
  text?: string;
  fare?: number | null;
}

export interface TrainOption {
  train_number: string;
  train_name: string;
  train_type?: string;
  train_type_label?: string;
  from_station_code?: string;
  from_station_name?: string;
  to_station_code?: string;
  to_station_name?: string;
  departure_time?: string;
  arrival_time?: string;
  duration_minutes?: number | null;
  classes?: TrainClass[];
  availability?: TrainAvailability[];
}

export interface TrainStation {
  code: string;
  name: string;
  city?: string;
  state?: string;
  kind?: "primary" | "fallback";
  side?: "origin" | "destination";
  is_major?: boolean;
}

export interface TrainsData {
  searched?: boolean;
  origin_station?: TrainStation;
  destination_station?: TrainStation;
  station_meta?: {
    origin?: TrainStation;
    destination?: TrainStation;
    origin_fallbacks?: TrainStation[];
    destination_fallbacks?: TrainStation[];
  };
  alternatives?: {
    primary_route?: { from?: string; from_name?: string; to?: string; to_name?: string };
    fallback_stations?: TrainStation[];
    ask_user?: boolean;
  };
  outbound_date?: string;
  return_date?: string;
  outbound?: TrainOption[];
  return?: TrainOption[];
}

export interface FlightsData {
  outbound?: FlightLegBundle;
  return_flights?: FlightLegBundle;
  airports?: unknown[];
  airport_meta?: {
    departure_airport_code?: string;
    arrival_airport_code?: string;
  };
  alternatives?: Record<string, unknown>;
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
  outboundTrainIndex?: number | null;
  returnTrainIndex?: number | null;
  hotelIndices?: number[];
}

export interface StreamEvent {
  type: string;
  node?: string;
  step_id?: string;
  label?: string;
  description?: string;
  payload?: Record<string, unknown>;
  ui_hints?: { open_tab?: TabId | null; show_package_card?: boolean };
  message?: string;
  content?: string;
  role?: string;
  snapshot?: TripSnapshot;
  thread_id?: string;
}
