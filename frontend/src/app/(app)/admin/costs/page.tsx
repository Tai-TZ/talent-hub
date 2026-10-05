import type { Metadata } from "next";
import { CostsView } from "@/features/admin/CostsView";

export const metadata: Metadata = { title: "Chi phí" };

export default function Page() {
  return <CostsView />;
}
