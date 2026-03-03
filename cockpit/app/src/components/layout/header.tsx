import { useLocation } from "react-router-dom";
import { Bell, Search, Plus } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";

const routeTitles: Record<string, { title: string; subtitle?: string }> = {
  "/": {
    title: "Dashboard",
    subtitle: "Overview of your codebase topology",
  },
  "/map": {
    title: "Ontology Map",
    subtitle: "3D spatial view of your architecture",
  },
  "/settings": {
    title: "Settings",
    subtitle: "Configure your workspace",
  },
  "/knowledge": {
    title: "Knowledge Base",
    subtitle: "Browse patterns and rules",
  },
  "/analytics": {
    title: "Analytics",
    subtitle: "Codebase metrics and insights",
  },
  "/agent": {
    title: "Agent",
    subtitle: "AI-powered navigation assistant",
  },
};

export function Header() {
  const { pathname } = useLocation();
  const route = routeTitles[pathname] || {
    title: "Ontology Map",
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-[var(--color-border-default)] bg-[var(--color-surface-0)]/80 px-6 backdrop-blur-xl">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-[var(--color-text-primary)]">
          {route.title}
        </h1>
        {route.subtitle && (
          <p className="text-[13px] text-[var(--color-text-tertiary)]">
            {route.subtitle}
          </p>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Search */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
        >
          <Search className="h-[18px] w-[18px]" />
        </Button>

        {/* Notifications */}
        <Button
          variant="ghost"
          size="icon"
          className="relative h-9 w-9 text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-1)] hover:text-[var(--color-text-primary)]"
        >
          <Bell className="h-[18px] w-[18px]" />
          <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--color-accent)]" />
        </Button>

        {/* Open project */}
        <Button className="ml-2 h-9 gap-1.5 rounded-[var(--radius-md)] bg-[var(--color-accent)] px-4 text-[13px] font-medium text-[var(--color-text-inverse)] transition-all hover:bg-[var(--color-accent-hover)] glow-accent-hover">
          <Plus className="h-4 w-4" />
          Open Project
        </Button>

        {/* User */}
        <Avatar className="ml-2 h-8 w-8 cursor-pointer border border-[var(--color-border-default)] transition-all hover:border-[var(--color-accent)]/30">
          <AvatarFallback className="bg-gradient-to-br from-[var(--color-accent)] to-[var(--color-secondary)] text-[11px] font-semibold text-white">
            GS
          </AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
