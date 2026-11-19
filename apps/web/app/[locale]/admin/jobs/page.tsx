import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { JobsPanel } from "@/components/admin/JobsPanel";

export const metadata: Metadata = { title: "Админка — ЖКХ AI ЮРИСТ", robots: { index: false } };

export default function Page() {
  return (
    <AdminShell>
      <JobsPanel />
    </AdminShell>
  );
}
