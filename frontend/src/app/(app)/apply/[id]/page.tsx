import type { Metadata } from "next";
import { ApplicationPage } from "@/features/apply/ApplicationPage";

export const metadata: Metadata = { title: "Hồ sơ ứng tuyển" };

export default async function ApplicationRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ApplicationPage id={id} />;
}
