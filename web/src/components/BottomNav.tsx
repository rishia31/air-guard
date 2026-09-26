"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, MessageCircle, Users, Settings } from "lucide-react";
import { useUser } from "@/lib/useUser";

export function BottomNav() {
  const pathname = usePathname();
  const { userLink } = useUser();

  const navItems = [
    { label: "Home", href: "/", icon: Activity },
    { label: "Talk", href: "/talk/", icon: MessageCircle },
    { label: "Community", href: "/community/", icon: Users },
    { label: "Settings", href: "/settings/", icon: Settings },
  ];

  return (
    <nav
      aria-label="Bottom Navigation"
      className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur border-t border-slate-200"
    >
      <div className="max-w-md mx-auto flex items-center justify-around h-16 px-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            item.href === "/"
              ? pathname === "/" || pathname === ""
              : pathname?.startsWith(item.href);

          return (
            <Link
              key={item.label}
              href={userLink(item.href)}
              className={`flex flex-col items-center justify-center flex-1 py-1 transition-colors ${
                isActive
                  ? "text-emerald-600 font-semibold"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              <Icon className="w-5 h-5 mb-1" />
              <span className="text-xs tracking-tight">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
