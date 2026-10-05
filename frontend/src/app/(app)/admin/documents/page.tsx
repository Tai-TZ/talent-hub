import type { Metadata } from "next";
import { DocumentsView } from "@/features/admin/DocumentsView";

export const metadata: Metadata = { title: "Tài liệu" };

export default function Page() {
  return <DocumentsView />;
}
