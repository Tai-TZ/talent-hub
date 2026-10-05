import type { Metadata } from "next";
import { ApplyHome } from "@/features/apply/ApplyHome";

export const metadata: Metadata = { title: "Hồ sơ của tôi" };

export default function ApplyPage() {
  return <ApplyHome />;
}
