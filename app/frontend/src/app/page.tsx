"use client";

import { ChatPanel } from "@/components/chat/ChatPanel";
import { ResultsPanel } from "@/components/results/ResultsPanel";
import { useSafarTrip } from "@/hooks/useSafarTrip";

export default function HomePage() {
  const trip = useSafarTrip();

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header className="shrink-0 flex items-center justify-between px-6 py-3 bg-white border-b shadow-sm z-10">
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold text-safar-red tracking-tight">Safar AI</span>
          <span className="text-xs text-gray-400 hidden sm:inline">
            Conversation-based trip planner
          </span>
        </div>
        <button
          type="button"
          onClick={() => trip.newTrip()}
          className="text-sm text-safar-navy hover:underline"
        >
          New trip
        </button>
      </header>

      <main className="flex-1 min-h-0 overflow-hidden grid grid-cols-1 lg:grid-cols-[minmax(320px,40%)_1fr]">
        <ChatPanel
          messages={trip.messages}
          steps={trip.steps}
          isStreaming={trip.isStreaming}
          showPackageCard={trip.showPackageCard}
          onSend={trip.sendMessage}
          onPackageSelect={trip.setActiveTab}
          structured={trip.structured}
          followUp={trip.interrupt}
        />
        <ResultsPanel
          activeTab={trip.activeTab}
          setActiveTab={trip.setActiveTab}
          itinerarySubTab={trip.itinerarySubTab}
          setItinerarySubTab={trip.setItinerarySubTab}
          structured={trip.structured}
          itinerary={trip.itinerary}
          weather={trip.weather}
          destinationAbout={trip.destinationAbout}
          flights={trip.flights}
          hotels={trip.hotels}
          selections={trip.selections}
          onSelections={trip.updateSelections}
        />
      </main>
    </div>
  );
}
