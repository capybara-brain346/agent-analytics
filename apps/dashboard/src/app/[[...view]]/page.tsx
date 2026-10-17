import { Suspense } from "react";
import { Dashboard } from "@/components/dashboard/dashboard";

export default function Page() {
  return (
    <Suspense fallback={<div className="app-loading">Opening workspace…</div>}>
      <Dashboard />
    </Suspense>
  );
}
