import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { ActsPanel } from "@/components/admin/ActsPanel";

export const metadata: Metadata = { title: "Админка — ЖКХ AI ЮРИСТ", robots: { index: false } };

export default function Page() {
  return (
    <AdminShell>
      <ActsPanel />
    </AdminShell>
  );
}
