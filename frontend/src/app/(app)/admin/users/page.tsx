import type { Metadata } from "next";
import { UsersView } from "@/features/admin/UsersView";

export const metadata: Metadata = { title: "Tài khoản" };

export default function Page() {
  return <UsersView />;
}
