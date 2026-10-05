import type { Metadata } from "next";
import { MentorView } from "@/features/cohorts/MentorView";

export const metadata: Metadata = { title: "Học viên của tôi" };

export default function MentorPage() {
  return <MentorView />;
}
