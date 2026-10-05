import type { Metadata } from "next";
import { IntakesView } from "@/features/intakes/IntakesView";

export const metadata: Metadata = { title: "Đợt tuyển" };

export default function IntakesPage() {
  return <IntakesView />;
}
