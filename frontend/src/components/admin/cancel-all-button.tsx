"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export function CancelAllButton() {
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleClick = async () => {
    if (!confirm("Cancel all active generations?")) return;
    setLoading(true);
    try {
      const res = await fetch("/api/tasks/cancel-all", { method: "POST" });
      if (res.ok) router.refresh();
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className="inline-flex items-center gap-1.5 rounded bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:opacity-90 disabled:opacity-50"
    >
      {loading && <Loader2 className="w-3 h-3 animate-spin" />}
      Cancel All
    </button>
  );
}
