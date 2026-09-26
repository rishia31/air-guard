"use client";

import { HeartHandshake } from "lucide-react";

export default function BuddyPage() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-amber-50 text-amber-600 flex items-center justify-center mb-4 border border-amber-100">
        <HeartHandshake className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-2">Buddy Phone</h1>
      <p className="text-sm text-slate-500 max-w-xs mb-6">
        Mutual asthma buddy support, companion check-ins, and proactive nudge alerts.
      </p>
      <div className="inline-flex items-center space-x-2 text-xs text-slate-400 bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-xs">
        <span>Owner: A4 (community-care)</span>
      </div>
    </div>
  );
}
