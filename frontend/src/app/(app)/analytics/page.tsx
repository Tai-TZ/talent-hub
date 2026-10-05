import type { Metadata } from "next";
import { AnalyticsView } from "@/features/analytics/AnalyticsView";

export const metadata: Metadata = { title: "Phễu và công bằng" };

export default function AnalyticsPage() {
  return <AnalyticsView />;
}
