"use client";

import { Suspense } from "react";
import { Header } from "./Header";
import { BottomNav } from "./BottomNav";
import { useStream } from "@/lib/useStream";
import { useUser } from "@/lib/useUser";

function AppShellContent({ children }: { children: React.ReactNode }) {
  const { userId } = useUser();
  const { connected } = useStream({ userId });

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col font-sans selection:bg-emerald-100 selection:text-emerald-900">
      <Header connected={connected} />
      
      <main className="flex-1 w-full max-w-md mx-auto px-4 pt-3 pb-24">
        {children}
      </main>

      <BottomNav />
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center bg-slate-50 text-slate-400">
          <div className="text-sm">Loading Airmate...</div>
        </div>
      }
    >
      <AppShellContent>{children}</AppShellContent>
    </Suspense>
  );
}
