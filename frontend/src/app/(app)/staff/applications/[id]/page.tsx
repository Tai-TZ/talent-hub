import type { Metadata } from "next";
import { Workbench } from "@/features/staff/Workbench";

export const metadata: Metadata = { title: "Bàn làm việc hồ sơ" };

export default async function WorkbenchPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Workbench id={id} />;
}
