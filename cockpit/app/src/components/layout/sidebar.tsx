import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  LayoutDashboard,
  Map,
  BookOpen,
  BarChart3,
  MessageSquare,
  Settings,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  LogOut,
  Search,
  Zap,
} from "lucide-react";

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  LayoutDashboard,
  Map,
  BookOpen,
  BarChart3,
  MessageSquare,
  Settings,
  Zap,
};

interface NavItem {
  label: string;
  href: string;
  icon: string;
  badge?: number;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/", icon: "LayoutDashboard" },
  { label: "Map", href: "/map", icon: "Map" },
  { label: "Knowledge", href: "/knowledge", icon: "BookOpen" },
  { label: "Analytics", href: "/analytics", icon: "BarChart3" },
  { label: "Agent", href: "/agent", icon: "Zap", badge: 1 },
];

const bottomItems: NavItem[] = [
  { label: "Settings", href: "/settings", icon: "Settings" },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const { pathname } = useLocation();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-[var(--color-border-default)] bg-[var(--color-surface-0)] transition-all duration-300",
        collapsed ? "w-[72px]" : "w-[260px]"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 px-5">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-muted)]">
          <Sparkles className="h-5 w-5 text-[var(--color-accent)]" />
        </div>
        {!collapsed && (
          <span className="text-[15px] font-semibold tracking-tight text-[var(--color-text-primary)]">
            Ontology Map
          </span>
        )}
      </div>

      <Separator />

      {/* Search trigger */}
      {!collapsed && (
        <div className="px-3 py-3">
          <div className="flex h-9 items-center gap-2 rounded-[var(--radius-md)] bg-[var(--color-surface-1)] px-3 text-[13px] text-[var(--color-text-tertiary)]">
            <Search className="h-4 w-4 shrink-0" />
            <span>Search...</span>
            <kbd className="ml-auto rounded bg-[var(--color-surface-2)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
              /
            </kbd>
          </div>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
        <p
          className={cn(
            "mb-2 text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-tertiary)]",
            collapsed && "text-center"
          )}
        >
          {collapsed ? "---" : "Navigation"}
        </p>
        {navItems.map((item) => {
          const Icon = iconMap[item.icon] || LayoutDashboard;
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));

          const link = (
            <Link
              key={item.label}
              to={item.href}
              className={cn(
                "group flex h-10 items-center gap-3 rounded-[var(--radius-md)] px-3 text-[13px] font-medium transition-all duration-200",
                isActive
                  ? "bg-[var(--color-accent-muted)] text-[var(--color-accent)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
              )}
            >
              <Icon
                className={cn(
                  "h-[18px] w-[18px] shrink-0 transition-colors",
                  isActive
                    ? "text-[var(--color-accent)]"
                    : "text-[var(--color-text-tertiary)] group-hover:text-[var(--color-text-secondary)]"
                )}
              />
              {!collapsed && (
                <>
                  <span className="flex-1">{item.label}</span>
                  {item.badge && (
                    <Badge
                      variant="secondary"
                      className="h-5 min-w-5 justify-center rounded-full bg-[var(--color-accent-muted)] px-1.5 text-[10px] font-semibold text-[var(--color-accent)]"
                    >
                      {item.badge}
                    </Badge>
                  )}
                </>
              )}
            </Link>
          );

          if (collapsed) {
            return (
              <Tooltip key={item.label}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">
                  {item.label}
                  {item.badge ? ` (${item.badge})` : ""}
                </TooltipContent>
              </Tooltip>
            );
          }

          return link;
        })}
      </nav>

      {/* Bottom section */}
      <div className="space-y-1 px-3 pb-2">
        {bottomItems.map((item) => {
          const Icon = iconMap[item.icon] || Settings;
          return (
            <Link
              key={item.label}
              to={item.href}
              className="group flex h-10 items-center gap-3 rounded-[var(--radius-md)] px-3 text-[13px] font-medium text-[var(--color-text-secondary)] transition-all hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
            >
              <Icon className="h-[18px] w-[18px] shrink-0 text-[var(--color-text-tertiary)] group-hover:text-[var(--color-text-secondary)]" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </div>

      <Separator />

      {/* User profile */}
      <div className="flex items-center gap-3 px-4 py-3">
        <Avatar className="h-8 w-8 shrink-0 border border-[var(--color-border-default)]">
          <AvatarFallback className="bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-secondary)] text-[11px] font-semibold text-white">
            GS
          </AvatarFallback>
        </Avatar>
        {!collapsed && (
          <div className="flex-1 overflow-hidden">
            <p className="truncate text-[13px] font-medium text-[var(--color-text-primary)]">
              Developer
            </p>
            <p className="truncate text-[11px] text-[var(--color-text-tertiary)]">
              Local Mode
            </p>
          </div>
        )}
        {!collapsed && (
          <button className="rounded-[var(--radius-sm)] p-1 text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-secondary)]">
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 flex h-6 w-6 items-center justify-center rounded-full border border-[var(--color-border-default)] bg-[var(--color-surface-1)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3" />
        ) : (
          <ChevronLeft className="h-3 w-3" />
        )}
      </button>
    </aside>
  );
}
