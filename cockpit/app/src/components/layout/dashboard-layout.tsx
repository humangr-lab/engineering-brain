import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "./sidebar";
import { Header } from "./header";

interface DashboardLayoutProps {
  children: ReactNode;
}

export function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <TooltipProvider delayDuration={600}>
      <div className="flex h-full">
        <Sidebar />
        {/* Main content area — offset by sidebar width */}
        <div className="ml-[260px] flex flex-1 flex-col transition-all duration-300">
          <Header />
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
      </div>
    </TooltipProvider>
  );
}
