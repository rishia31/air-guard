"use client";

import { Users, MapPin } from "lucide-react";

export default function CommunityPage() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100">
        <Users className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-2">Community & Hotspots</h1>
      <p className="text-sm text-slate-500 max-w-xs mb-6">
        Anonymized air quality heatmaps and local asthma circle discussions.
      </p>
      <div className="inline-flex items-center space-x-2 text-xs text-slate-400 bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-xs">
        <MapPin className="w-3.5 h-3.5 text-emerald-500" />
        <span>Owner: A4 (community-care)</span>
      </div>
    </div>
  );
}
