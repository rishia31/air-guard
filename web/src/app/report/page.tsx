"use client";

import { FileText } from "lucide-react";

export default function ReportPage() {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-blue-50 text-blue-600 flex items-center justify-center mb-4 border border-blue-100">
        <FileText className="w-7 h-7" />
      </div>
      <h1 className="text-xl font-bold text-slate-900 mb-2">Doctor Clinical Report</h1>
      <p className="text-sm text-slate-500 max-w-xs mb-6">
        Shareable, printable clinical summary of symptoms, risk trends, and exposures for your clinician.
      </p>
      <div className="inline-flex items-center space-x-2 text-xs text-slate-400 bg-white border border-slate-200 px-3 py-1.5 rounded-full shadow-xs">
        <span>Owner: A4 (community-care)</span>
      </div>
    </div>
  );
}
