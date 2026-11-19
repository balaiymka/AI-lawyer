"use client";

import { useEffect, useState } from "react";

import { JobStatus, JobWatcher } from "@/components/admin/JobWatcher";
import { adminFetch, ruDateTime, type Job } from "@/lib/admin";

export function JobsPanel() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    let stop = false;
    let t: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const js = await adminFetch<Job[]>("/v1/admin/jobs");
        if (!stop) setJobs(js);
      } catch {}
      if (!stop) t = setTimeout(tick, 3000);
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, []);
  return (
    <>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Задачи</h1>
        <p className="text-sm text-muted">Загрузка редакций, проверка обновлений и индексация — выполняются по одной в фоне</p>
      </div>
      {open && <JobWatcher key={open} jobId={open} />}
      <div className="glass overflow-x-auto rounded-[24px]">
        <table className="w-full min-w-[620px] text-sm">
          <thead><tr className="border-b border-line text-left text-xs text-muted">
            <th className="px-4 py-3 font-medium">Задача</th><th className="px-4 py-3 font-medium">Статус</th>
            <th className="px-4 py-3 font-medium">Запустил</th><th className="px-4 py-3 font-medium">Начало</th><th className="px-4 py-3" />
          </tr></thead>
          <tbody>
            {jobs?.length === 0 && <tr><td colSpan={5} className="px-4 py-6 text-muted">Задач пока не было. Они появятся после запуска из раздела «Законы».</td></tr>}
            {jobs?.map((j) => (
              <tr key={j.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-3">{j.title}{j.error && <p className="text-xs text-danger">{j.error}</p>}</td>
                <td className="px-4 py-3"><JobStatus status={j.status} /></td>
                <td className="px-4 py-3 text-xs text-muted">{j.created_by}</td>
                <td className="px-4 py-3 text-xs text-muted tabular">{ruDateTime(j.created_at)}</td>
                <td className="px-4 py-3 text-right"><button type="button" onClick={() => setOpen(j.id)} className="rounded-full border border-line px-3 py-1 text-xs hover:bg-surface-2">Журнал</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
