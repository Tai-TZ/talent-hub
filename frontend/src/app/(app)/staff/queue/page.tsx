import type { Metadata } from "next";
import { QueueView } from "@/features/staff/QueueView";

export const metadata: Metadata = { title: "Hàng đợi hồ sơ" };

export default function QueuePage() {
  return <QueueView />;
}
