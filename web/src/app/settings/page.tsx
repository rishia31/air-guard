"use client";

import { Settings as SettingsIcon, Sliders } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-slate-100 text-slate-700 flex items-center justify-center mb-4 border border-slate-200">
        <SettingsIcon className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-2">Settings & Action Plan</h1>
      <p className="text-sm text-slate-500 max-w-xs mb-6">
        Manage triggers, review clinical action plan, link buddies and doctor info.
      </p>
      <div className="inline-flex items-center space-x-2 text-xs text-slate-600 bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-full shadow-xs">
        <Sliders className="w-3.5 h-3.5" />
        <span>Settings configuration ready for Task 6</span>
      </div>
    </div>
  );
}
