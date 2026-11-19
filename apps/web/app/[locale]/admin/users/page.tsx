import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { UsersPanel } from "@/components/admin/UsersPanel";

export const metadata: Metadata = { title: "Админка — ЖКХ AI ЮРИСТ", robots: { index: false } };

export default function Page() {
  return (
    <AdminShell>
      <UsersPanel />
    </AdminShell>
  );
}
