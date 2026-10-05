import type { Metadata } from "next";
import { LabView } from "@/features/analytics/LabView";

export const metadata: Metadata = { title: "Rubric Lab" };

export default function LabPage() {
  return <LabView />;
}
