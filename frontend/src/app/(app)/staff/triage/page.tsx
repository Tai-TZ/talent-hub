import type { Metadata } from "next";
import { TriageView } from "@/features/staff/TriageView";

export const metadata: Metadata = { title: "Sàng lọc AI" };

export default function TriagePage() {
  return <TriageView />;
}
