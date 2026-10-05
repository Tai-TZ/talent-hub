import type { Metadata } from "next";
import { IntakeDetail } from "@/features/intakes/IntakeDetail";

export const metadata: Metadata = { title: "Chi tiết đợt tuyển" };

export default async function IntakeDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <IntakeDetail id={id} />;
}
