"use client";

import { useState } from "react";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { ResultsPanel } from "@/components/results/ResultsPanel";
import { Sidebar } from "@/components/Sidebar";
import { useSafarTrip } from "@/hooks/useSafarTrip";

export default function HomePage() {
  const trip = useSafarTrip();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <header className="shrink-0 flex items-center justify-between px-6 py-3 bg-white border-b shadow-sm z-10">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-500 hover:text-gray-700 transition-colors"
            title="Toggle trip history"
            aria-label="Toggle trip history"
          >
            ☰
          </button>
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

      <main className="flex-1 min-h-0 overflow-hidden flex flex-row">
        <Sidebar
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(false)}
          savedTrips={trip.savedTrips || []}
          activeThreadId={trip.threadId}
          onSelectTrip={trip.switchTrip}
          onDeleteTrip={trip.removeTrip}
          onNewTrip={trip.newTrip}
        />
        <div className="flex-1 min-h-0 overflow-hidden grid grid-cols-1 lg:grid-cols-[minmax(320px,40%)_1fr]">
          <ChatPanel
            messages={trip.messages}
            steps={trip.steps}
            isStreaming={trip.isStreaming}
            isLoading={trip.isLoadingThread}
            showPackageCard={trip.showPackageCard}
            onSend={trip.sendMessage}
            onPackageSelect={trip.setActiveTab}
            structured={trip.structured}
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
            trains={trip.trains}
            hotels={trip.hotels}
            selections={trip.selections}
            onSelections={trip.updateSelections}
            awaitingPlanUpdate={trip.awaitingPlanUpdate}
            onConfirmPlanUpdate={trip.confirmPlanUpdate}
            onKeepPlan={trip.keepPlan}
          />
        </div>
      </main>
    </div>
  );
}
