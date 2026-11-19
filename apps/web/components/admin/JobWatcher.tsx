"use client";

import { clsx } from "clsx";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { adminFetch, type Job } from "@/lib/admin";

export function JobStatus({ status }: { status: Job["status"] }) {
  const map = {
    queued: ["в очереди", "text-muted", Loader2],
    running: ["выполняется", "text-electric", Loader2],
    done: ["готово", "text-success", CheckCircle2],
    failed: ["ошибка", "text-danger", XCircle],
  } as const;
  const [label, cls, Icon] = map[status];
  return (
    <span className={clsx("inline-flex items-center gap-1 text-xs font-semibold", cls)}>
      <Icon className={clsx("size-3.5", (status === "running" || status === "queued") && "animate-spin")} aria-hidden />
      {label}
    </span>
  );
}

// Следит за задачей, пока она не завершится; показывает хвост журнала.
export function JobWatcher({ jobId, onFinish }: { jobId: string; onFinish?: (j: Job) => void }) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const j = await adminFetch<Job>(`/v1/admin/jobs/${jobId}`);
        if (stop) return;
        setJob(j);
        if (j.status === "done" || j.status === "failed") {
          onFinish?.(j);
          return;
        }
      } catch {}
      timer = setTimeout(tick, 1500);
    };
    void tick();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  if (!job) return null;
  return (
    <div className="rounded-2xl border border-line bg-surface-2 p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">{job.title}</span>
        <JobStatus status={job.status} />
      </div>
      <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-muted">{job.log.slice(-8).join("\n")}</pre>
      {job.error && <p className="mt-1 text-danger">{job.error}</p>}
    </div>
  );
}
