"use client";

import { useUser } from "@/lib/useUser";
import { DEMO_USERS } from "@/lib/types";
import { ShieldCheck } from "lucide-react";

interface HeaderProps {
  connected?: boolean;
}

export function Header({ connected = true }: HeaderProps) {
  const { userId, setUserId } = useUser();

  return (
    <header className="sticky top-0 z-30 bg-white/95 backdrop-blur border-b border-slate-200">
      <div className="max-w-md mx-auto flex items-center justify-between h-14 px-4">
        {/* Brand */}
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-xl bg-emerald-500 flex items-center justify-center text-white shadow-sm shadow-emerald-200">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-slate-900 tracking-tight text-base">Airmate</span>
            <span className="ml-1 text-[10px] uppercase font-semibold tracking-wider text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded-full border border-emerald-200">
              Live
            </span>
          </div>
        </div>

        {/* Live indicator & Demo persona switcher */}
        <div className="flex items-center space-x-3">
          <div
            className="flex items-center space-x-1 text-xs text-slate-500"
            title={connected ? "Connected to live stream" : "Reconnecting to live stream..."}
          >
            {connected ? (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
            ) : (
              <span className="inline-flex rounded-full h-2 w-2 bg-amber-400 animate-pulse"></span>
            )}
          </div>

          <label htmlFor="user-select" className="sr-only">
            Active user
          </label>
          <select
            id="user-select"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="text-xs font-medium bg-slate-100 hover:bg-slate-200/80 text-slate-700 py-1 px-2.5 rounded-lg border-0 focus:ring-2 focus:ring-emerald-500 cursor-pointer capitalize transition-colors"
          >
            {DEMO_USERS.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </select>
        </div>
      </div>
    </header>
  );
}
