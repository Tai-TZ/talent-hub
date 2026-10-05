import type { Metadata } from "next";
import { IntegrationsView } from "@/features/admin/IntegrationsView";
import { integrationMessages } from "@/features/admin/integrations-messages";
import { getMessagesFor } from "@/lib/server";

export async function generateMetadata(): Promise<Metadata> {
  return { title: (await getMessagesFor(integrationMessages)).title };
}

export default function Page() {
  return <IntegrationsView />;
}
