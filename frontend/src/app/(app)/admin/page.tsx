import type { Metadata } from "next";
import { OverviewView } from "@/features/admin/OverviewView";

export const metadata: Metadata = { title: "Tổng quan hệ thống" };

export default function Page() {
  return <OverviewView />;
}
