"use client";

import {
  BarChart3,
  ContactRound,
  LayoutDashboard,
  Music4,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const iconMap = {
  dashboard: LayoutDashboard,
  campaigns: BarChart3,
  contacts: ContactRound,
  audio: Music4,
} satisfies Record<string, LucideIcon>;

type NavigationItem = {
  href: string;
  label: string;
  icon: keyof typeof iconMap;
};

export function SidebarNav({ items }: { items: NavigationItem[] }) {
  const pathname = usePathname();

  return (
    <nav className="space-y-2.5">
      {items.map((item) => {
        const Icon = iconMap[item.icon];
        const isActive =
          pathname === item.href ||
          (item.href !== "/dashboard" && pathname.startsWith(item.href));

        return (
          <Link
            key={item.href}
            href={item.href}
            className={`dashboard-nav-item ${isActive ? "dashboard-nav-item-active" : "dashboard-nav-item-idle"}`}
          >
            <span
              className={`flex size-8 items-center justify-center rounded-full transition ${isActive ? "bg-white text-violet-600 shadow-[0_12px_30px_rgba(255,255,255,0.28)]" : "bg-white/10 text-white/90"}`}
            >
              <Icon className="size-4" />
            </span>
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
