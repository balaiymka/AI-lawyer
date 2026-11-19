import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { StatusPanel } from "@/components/admin/StatusPanel";

export const metadata: Metadata = { title: "Админка — ЖКХ AI ЮРИСТ", robots: { index: false } };

export default function Page() {
  return (
    <AdminShell>
      <StatusPanel />
    </AdminShell>
  );
}
