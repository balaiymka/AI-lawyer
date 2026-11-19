import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { ReviewPanel } from "@/components/admin/ReviewPanel";

export const metadata: Metadata = { title: "Админка — ЖКХ AI ЮРИСТ", robots: { index: false } };

export default function Page() {
  return (
    <AdminShell>
      <ReviewPanel />
    </AdminShell>
  );
}
