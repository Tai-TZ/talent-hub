import type { Metadata } from "next";
import { SettingsView } from "@/features/admin/SettingsView";

export const metadata: Metadata = { title: "Cài đặt" };

export default function Page() {
  return <SettingsView />;
}
