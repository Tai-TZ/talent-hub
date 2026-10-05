import type { Metadata } from "next";
import { CohortsView } from "@/features/cohorts/CohortsView";

export const metadata: Metadata = { title: "Khoá học" };

export default function CohortsPage() {
  return <CohortsView />;
}
