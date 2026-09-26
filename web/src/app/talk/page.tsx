"use client";

import { MessageSquare, Mic } from "lucide-react";

export default function TalkPage() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 flex items-center justify-center mb-4 border border-emerald-100">
        <MessageSquare className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-2">Talk with Airmate</h1>
      <p className="text-sm text-slate-500 max-w-xs mb-6">
        Voice and chat companion powered by Grok, checking triggers and guiding action plans safely.
      </p>
      <div className="inline-flex items-center space-x-2 text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-full shadow-xs">
        <Mic className="w-3.5 h-3.5" />
        <span>Airmate voice & chat ready for Task 5</span>
      </div>
    </div>
  );
}
