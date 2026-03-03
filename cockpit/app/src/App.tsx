import { Routes, Route } from "react-router-dom";
import { Suspense, lazy } from "react";
import { DashboardLayout } from "@/components/layout/dashboard-layout";

const MapPage = lazy(() => import("@/pages/map"));
const DashboardPage = lazy(() => import("@/pages/dashboard"));
const SettingsPage = lazy(() => import("@/pages/settings"));

function LoadingFallback() {
  return (
    <div className="flex h-full items-center justify-center bg-[var(--color-surface-0)]">
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
        <span className="text-sm text-[var(--color-text-secondary)]">
          Loading...
        </span>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <div className="noise-bg h-full">
      <DashboardLayout>
        <Suspense fallback={<LoadingFallback />}>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </Suspense>
      </DashboardLayout>
    </div>
  );
}
