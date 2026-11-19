import { notFound } from "next/navigation";

import { ChatView } from "@/components/chat/ChatView";
import type { Role } from "@/lib/chat";
import { getDictionary, isLocale } from "@/lib/i18n";

const ROLES = ["owner", "osi", "uk", "lawyer"];

export default async function ChatPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ q?: string; role?: string; case?: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const { q, role, case: caseId } = await searchParams;
  const t = getDictionary(locale);
  const validCase = caseId && /^[0-9a-f-]{36}$/.test(caseId) ? caseId : undefined;
  return (
    <ChatView t={t} initialQ={validCase ? undefined : q} initialCase={validCase}
      role={role && ROLES.includes(role) ? (role as Role) : undefined} />
  );
}
