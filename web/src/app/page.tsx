"use client";

import { useEffect, useState } from "react";
import { useUser } from "@/lib/useUser";
import { useStream } from "@/lib/useStream";
import { api } from "@/lib/api";
import type { RiskOut, TypedStreamMessage } from "@/lib/types";
import { BAND_COLORS } from "@/lib/types";
import { AlertCircle, Sparkles } from "lucide-react";

export default function DashboardPage() {
  const { userId } = useUser();
  const [risk, setRisk] = useState<RiskOut | null>(null);
  const [loading, setLoading] = useState(true);

  // Initial fetch
  useEffect(() => {
    let active = true;
    api
      .getUserRisk(userId)
      .then((data) => {
        if (active) {
          setRisk(data);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.warn("Could not load initial risk:", err);
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [userId]);

  // Handle live stream updates
  useStream({
    userId,
    onMessage: (msg: TypedStreamMessage) => {
      if (msg.type === "risk" && msg.data) {
        setRisk(msg.data as RiskOut);
      }
    },
  });

  const score = risk?.score ?? 0;
  const band = risk?.band ?? "low";
  const bandColor = risk?.color ?? BAND_COLORS[band];

  return (
    <div className="space-y-4">
      {/* Risk Summary Card */}
      <section className="bg-white rounded-2xl p-6 shadow-xs border border-slate-100 flex flex-col items-center text-center">
        <span className="text-xs uppercase font-semibold tracking-wider text-slate-400 mb-1">
          Asthma Risk Score (Next 4h)
        </span>

        {/* Ring indicator */}
        <div
          className="relative w-40 h-40 rounded-full flex flex-col items-center justify-center my-3 transition-colors duration-500"
          style={{
            background: `radial-gradient(closest-side, white 79%, transparent 80% 100%), conic-gradient(${bandColor} ${score}%, #e2e8f0 0)`,
          }}
        >
          <span className="text-5xl font-black tracking-tight text-slate-900">
            {loading && !risk ? "--" : score}
          </span>
          <span
            className="text-xs font-bold uppercase tracking-wider mt-1 px-2.5 py-0.5 rounded-full"
            style={{
              color: bandColor,
              backgroundColor: `${bandColor}15`,
            }}
          >
            {band}
          </span>
        </div>

        {/* Top Factor / Why */}
        {risk?.factors && risk.factors.length > 0 ? (
          <div className="w-full mt-2 p-3 bg-slate-50 rounded-xl border border-slate-100 text-left">
            <div className="flex items-center space-x-1.5 text-xs font-medium text-slate-500 mb-1">
              <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
              <span>Primary Driver</span>
            </div>
            <p className="text-sm font-medium text-slate-800">
              {risk.factors[0].detail || `${risk.factors[0].label} elevates risk.`}
            </p>
          </div>
        ) : (
          <p className="text-xs text-slate-500 mt-2">
            Air is currently within your baseline parameters.
          </p>
        )}
      </section>

      {/* Model Mode Pill */}
      <div className="flex items-center justify-between px-2 text-xs text-slate-400">
        <span className="flex items-center space-x-1">
          <Sparkles className="w-3.5 h-3.5 text-emerald-500" />
          <span>
            {risk?.model?.name === "rules" ? "Basic mode (rules)" : "ML survival model"}
          </span>
        </span>
        <span className="capitalize">{userId}&apos;s Room</span>
      </div>

      {/* Footer Disclaimer */}
      <footer className="pt-6 pb-2 text-center">
        <p className="text-[11px] text-slate-400 leading-relaxed max-w-xs mx-auto">
          Risk model trained on simulated data. Not a medical device. Always consult your physician.
        </p>
      </footer>
    </div>
  );
}
