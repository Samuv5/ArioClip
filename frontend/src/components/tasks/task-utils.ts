import { formatSupportMessage, parseApiError } from "@/lib/api-error";

export const getClipUrl = (videoUrl: string) =>
  videoUrl.startsWith("/api/") ? videoUrl : `/api${videoUrl}`;

export const formatDuration = (seconds: number) => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
};

export const getScoreColor = (score: number) => {
  if (score >= 0.8) return "bg-green-100 text-green-800";
  if (score >= 0.6) return "bg-yellow-100 text-yellow-800";
  return "bg-red-100 text-red-800";
};

export const getViralityColor = (score: number) => {
  if (score >= 80) return "text-green-600";
  if (score >= 60) return "text-yellow-600";
  if (score >= 40) return "text-orange-600";
  return "text-red-600";
};

export const getViralityBgColor = (score: number) => {
  if (score >= 80) return "bg-green-500";
  if (score >= 60) return "bg-yellow-500";
  if (score >= 40) return "bg-orange-500";
  return "bg-red-500";
};

export const getHookTypeLabel = (hookType: string | null) => {
  const labels: Record<string, string> = {
    question: "Question Hook",
    statement: "Bold Statement",
    statistic: "Data/Stats",
    story: "Story Hook",
    contrast: "Contrast Hook",
    none: "No Hook",
  };
  return labels[hookType || "none"] || hookType || "None";
};

export const buildSupportError = async (response: Response, fallbackMessage: string) => {
  const parsed = await parseApiError(response, fallbackMessage);
  return formatSupportMessage(parsed);
};
