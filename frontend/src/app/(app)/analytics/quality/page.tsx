import type { Metadata } from "next";
import { QualityView } from "@/features/analytics/QualityView";
import { qualityMessages } from "@/features/analytics/quality-messages";
import { getMessagesFor } from "@/lib/server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getMessagesFor(qualityMessages)).title };
}

export default function QualityPage() {
  return <QualityView />;
}
