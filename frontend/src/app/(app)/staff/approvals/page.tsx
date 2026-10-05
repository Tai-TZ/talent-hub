import type { Metadata } from "next";
import { ApprovalsView } from "@/features/staff/ApprovalsView";

export const metadata: Metadata = { title: "Phê duyệt" };

export default function ApprovalsPage() {
  return <ApprovalsView />;
}
