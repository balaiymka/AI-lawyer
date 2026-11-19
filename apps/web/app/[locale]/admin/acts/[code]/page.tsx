import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { ActDetail } from "@/components/admin/ActDetail";
import { AdminShell } from "@/components/admin/AdminShell";

export const metadata: Metadata = { title: "Акт — админка", robots: { index: false } };

export default async function Page({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  if (!/^[A-Z][A-Z0-9_]{1,30}$/.test(code)) notFound();
  return (
    <AdminShell>
      <ActDetail code={code} />
    </AdminShell>
  );
}
