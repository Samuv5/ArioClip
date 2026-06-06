"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, ArrowLeft, Clock, Settings2, GitMerge } from "lucide-react";
import { useSession } from "@/lib/auth-client";
import Link from "next/link";
import type { Clip, TaskDetails, FontOption, CaptionTemplateOption, ExportPreset, CaptionPosition } from "@/components/tasks/types";
import { buildSupportError } from "@/components/tasks/task-utils";
import { TaskHeader } from "@/components/tasks/task-header";
import { ProcessingState } from "@/components/tasks/processing-state";
import { ClipCard } from "@/components/tasks/clip-card";
import { YouTubeUploadModal } from "@/components/tasks/youtube-upload-modal";
import { ProjectSettingsSheet } from "@/components/tasks/project-settings-sheet";
import { DeleteConfirmDialog } from "@/components/tasks/delete-confirm-dialog";

export default function TaskPage() {
  const params = useParams();
  const router = useRouter();
  const { data: session } = useSession();
  const [task, setTask] = useState<TaskDetails | null>(null);
  const [clips, setClips] = useState<Clip[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState("");
  const [subProgress, setSubProgress] = useState<number | null>(null);
  const [subMessage, setSubMessage] = useState<string | null>(null);
  const [progressMetadata, setProgressMetadata] = useState<Record<string, unknown> | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedTitle, setEditedTitle] = useState("");
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deletingClipId, setDeletingClipId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [selectedClipIds, setSelectedClipIds] = useState<string[]>([]);
  const [editingClipId, setEditingClipId] = useState<string | null>(null);
  const [startOffset, setStartOffset] = useState("0");
  const [endOffset, setEndOffset] = useState("0");
  const [splitTime, setSplitTime] = useState("5");
  const [captionText, setCaptionText] = useState("");
  const [captionPosition, setCaptionPosition] = useState<CaptionPosition>("bottom");
  const [highlightWords, setHighlightWords] = useState("");
  const [exportPreset, setExportPreset] = useState<ExportPreset>("original");

  const [projectFontFamily, setProjectFontFamily] = useState("TikTokSans-Regular");
  const [projectFontSize, setProjectFontSize] = useState("24");
  const [projectFontColor, setProjectFontColor] = useState("#FFFFFF");
  const [projectCaptionTemplate, setProjectCaptionTemplate] = useState("default");
  const [projectIncludeBroll, setProjectIncludeBroll] = useState(false);
  const [projectCutLongPauses, setProjectCutLongPauses] = useState(false);
  const [projectPauseThresholdMs, setProjectPauseThresholdMs] = useState("900");
  const [projectRemoveFillerWords, setProjectRemoveFillerWords] = useState(false);
  const [projectFilteredWords, setProjectFilteredWords] = useState("");
  const [isApplyingSettings, setIsApplyingSettings] = useState(false);
  const [settingsSheetOpen, setSettingsSheetOpen] = useState(false);
  const [availableFonts, setAvailableFonts] = useState<FontOption[]>([]);
  const [availableTemplates, setAvailableTemplates] = useState<CaptionTemplateOption[]>([]);
  const hasTriggeredAutoRefresh = useRef(false);

  // YouTube upload state
  const [youtubeModalClip, setYoutubeModalClip] = useState<Clip | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const taskApiUrl = "/api/tasks";

  const triggerAutoRefresh = useCallback(() => {
    if (hasTriggeredAutoRefresh.current) return;
    hasTriggeredAutoRefresh.current = true;
    setTimeout(() => {
      window.location.reload();
    }, 700);
  }, []);

  const fetchTaskStatus = useCallback(
    async (retryCount = 0, maxRetries = 5) => {
      if (!params.id) return false;

      try {
        const taskResponse = await fetch(`${taskApiUrl}/${params.id}`, {
          cache: "no-store",
        });

        if (taskResponse.status === 404 && retryCount < maxRetries) {
          console.log(
            `Task not found yet, retrying in ${(retryCount + 1) * 500}ms... (${retryCount + 1}/${maxRetries})`,
          );
          await new Promise((resolve) => setTimeout(resolve, (retryCount + 1) * 500));
          return fetchTaskStatus(retryCount + 1, maxRetries);
        }

        if (!taskResponse.ok) {
          throw new Error(await buildSupportError(taskResponse, `Failed to fetch task: ${taskResponse.status}`));
        }

        const taskData = await taskResponse.json();
        setTask(taskData);
        setProjectFontFamily(taskData.font_family || "TikTokSans-Regular");
        setProjectFontSize(String(taskData.font_size || 48));
        setProjectFontColor(taskData.font_color || "#FFFFFF");
        setProjectCaptionTemplate(taskData.caption_template || "default");
        setProjectIncludeBroll(Boolean(taskData.include_broll));
        setProjectCutLongPauses(Boolean(taskData.cut_long_pauses));
        setProjectPauseThresholdMs(String(taskData.pause_threshold_ms || 900));
        setProjectRemoveFillerWords(Boolean(taskData.remove_filler_words));
        setProjectFilteredWords((taskData.filtered_words || []).join(", "));

        if (taskData.status === "completed" || taskData.status === "processing") {
          const clipsResponse = await fetch(`${taskApiUrl}/${params.id}/clips`, {
            cache: "no-store",
          });

          if (!clipsResponse.ok) {
            throw new Error(await buildSupportError(clipsResponse, `Failed to fetch clips: ${clipsResponse.status}`));
          }

          const clipsData = await clipsResponse.json();
          const nextClips = clipsData.clips || [];
          setClips((prev) => {
            if (taskData.status === "completed") {
              return nextClips;
            }

            const merged = new Map<string, Clip>();
            for (const clip of prev) {
              merged.set(clip.id, clip);
            }
            for (const clip of nextClips) {
              merged.set(clip.id, clip);
            }
            return Array.from(merged.values()).sort(
              (a, b) => (a.clip_order ?? 0) - (b.clip_order ?? 0),
            );
          });
        }

        return true;
      } catch (err) {
        console.error("Error fetching task data:", err);
        setError(err instanceof Error ? err.message : "Failed to load task");
        return false;
      }
    },
    [params.id, taskApiUrl],
  );

  useEffect(() => {
    if (!params.id) return;

    const fetchTaskData = async () => {
      try {
        setIsLoading(true);
        await fetchTaskStatus();
      } finally {
        setIsLoading(false);
      }
    };

    fetchTaskData();
  }, [params.id, fetchTaskStatus]);

  useEffect(() => {
    const loadFonts = async () => {
      try {
        const response = await fetch("/api/fonts", { cache: "no-store" });
        if (!response.ok) return;
        const data = await response.json();
        setAvailableFonts(data.fonts || []);
      } catch { /* ignore */ }
    };

    void loadFonts();

    const loadTemplates = async () => {
      try {
        const response = await fetch(`${apiUrl}/caption-templates`);
        if (response.ok) {
          const data = await response.json();
          setAvailableTemplates(data.templates || []);
        }
      } catch { /* ignore */ }
    };
    void loadTemplates();
  }, [apiUrl]);

  useEffect(() => {
    const taskStatus = task?.status;
    if (!params.id || !taskStatus) return;

    if (taskStatus !== "queued" && taskStatus !== "processing") return;

    const eventSource = new EventSource(`${taskApiUrl}/${params.id}/progress`);

    eventSource.addEventListener("status", (e) => {
      const data = JSON.parse(e.data);
      setProgress(data.progress || 0);
      setProgressMessage(data.message || "");
      setSubProgress(data.sub_progress ?? null);
      setSubMessage(data.sub_message ?? null);
      setProgressMetadata(data.metadata ?? null);
      if (data.status === "completed") {
        void fetchTaskStatus().then(() => triggerAutoRefresh());
      }
    });

    eventSource.addEventListener("progress", (e) => {
      const data = JSON.parse(e.data);
      setProgress(data.progress || 0);
      setProgressMessage(data.message || "");
      setSubProgress(data.sub_progress ?? null);
      setSubMessage(data.sub_message ?? null);
      setProgressMetadata(data.metadata ?? null);
      if (data.status) {
        setTask((currentTask) => (currentTask ? { ...currentTask, status: data.status } : currentTask));
        if (data.status === "completed") {
          void fetchTaskStatus().then(() => triggerAutoRefresh());
        }
      }
    });

    eventSource.addEventListener("clip_ready", (e) => {
      const data = JSON.parse(e.data);
      if (data.clip) {
        setClips((prev) => {
          const exists = prev.some((c: Clip) => c.id === data.clip.id);
          if (exists) return prev;
          return [...prev, data.clip].sort(
            (a: Clip, b: Clip) => (a.clip_order ?? 0) - (b.clip_order ?? 0),
          );
        });
      }
    });

    eventSource.addEventListener("close", async () => {
      eventSource.close();
      await fetchTaskStatus();
      triggerAutoRefresh();
    });

    eventSource.addEventListener("error", (e) => {
      const maybeMessageEvent = e as MessageEvent<string>;
      if (typeof maybeMessageEvent.data === "string" && maybeMessageEvent.data.length > 0) {
        const data = JSON.parse(maybeMessageEvent.data);
        setError(data.error || "Connection error");
      }
      eventSource.close();
    });

    return () => {
      eventSource.close();
    };
  }, [params.id, task?.status, fetchTaskStatus, taskApiUrl, triggerAutoRefresh]);

  const handleEditTitle = async () => {
    if (!editedTitle.trim() || !session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${taskApiUrl}/${params.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: editedTitle }),
      });

      if (response.ok) {
        setTask(task ? { ...task, source_title: editedTitle } : null);
        setIsEditing(false);
      } else {
        alert(await buildSupportError(response, "Failed to update title"));
      }
    } catch (err) {
      console.error("Error updating title:", err);
      alert(err instanceof Error ? err.message : "Failed to update title");
    }
  };

  const handleDeleteTask = async () => {
    if (!session?.user?.id || !params.id) return;
    setIsDeleting(true);
    try {
      const response = await fetch(`${taskApiUrl}/${params.id}`, { method: "DELETE" });
      if (response.ok) {
        router.push("/list");
      } else {
        alert(await buildSupportError(response, "Failed to delete task"));
      }
    } catch (err) {
      console.error("Error deleting task:", err);
      alert(err instanceof Error ? err.message : "Failed to delete task");
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  const handleDeleteClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;

    try {
      const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}`, { method: "DELETE" });
      if (response.ok) {
        setClips(clips.filter((clip) => clip.id !== clipId));
        setDeletingClipId(null);
      } else {
        alert(await buildSupportError(response, "Failed to delete clip"));
      }
    } catch (err) {
      console.error("Error deleting clip:", err);
      alert(err instanceof Error ? err.message : "Failed to delete clip");
    }
  };

  const handleToggleClipSelection = (clipId: string) => {
    setSelectedClipIds((prev) => {
      if (prev.includes(clipId)) return prev.filter((id) => id !== clipId);
      return [...prev, clipId];
    });
  };

  const handleTrimClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        start_offset: Number(startOffset || "0"),
        end_offset: Number(endOffset || "0"),
      }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "Failed to trim clip"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleSplitClip = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ split_time: Number(splitTime || "5") }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "Failed to split clip"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleMergeClips = async () => {
    if (!session?.user?.id || !params.id || selectedClipIds.length < 2) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clip_ids: selectedClipIds }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "Failed to merge clips"));
      return;
    }
    setSelectedClipIds([]);
    await fetchTaskStatus();
  };

  const handleUpdateCaptions = async (clipId: string) => {
    if (!session?.user?.id || !params.id) return;
    const response = await fetch(`${taskApiUrl}/${params.id}/clips/${clipId}/captions`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        caption_text: captionText,
        position: captionPosition,
        highlight_words: highlightWords.split(",").map((w) => w.trim()).filter(Boolean),
      }),
    });
    if (!response.ok) {
      alert(await buildSupportError(response, "Failed to update captions"));
      return;
    }
    await fetchTaskStatus();
  };

  const handleApplyProjectSettings = async () => {
    if (!session?.user?.id || !params.id) return;
    const parsedSize = Number(projectFontSize || "24");
    const safeFontSize = Number.isFinite(parsedSize) ? Math.max(12, Math.min(72, Math.round(parsedSize))) : 24;
    const normalizedColor = /^#[0-9A-Fa-f]{6}$/.test(projectFontColor) ? projectFontColor : "#FFFFFF";
    const parsedPauseThreshold = Number(projectPauseThresholdMs || "900");
    const safePauseThreshold = Number.isFinite(parsedPauseThreshold)
      ? Math.max(250, Math.min(3000, Math.round(parsedPauseThreshold)))
      : 900;
    const normalizedFilteredWords = projectFilteredWords
      .split(",")
      .map((word) => word.trim().toLowerCase())
      .filter(Boolean);

    setIsApplyingSettings(true);
    try {
      const response = await fetch(`${taskApiUrl}/${params.id}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          font_family: projectFontFamily,
          font_size: safeFontSize,
          font_color: normalizedColor,
          caption_template: projectCaptionTemplate,
          include_broll: projectIncludeBroll,
          cut_long_pauses: projectCutLongPauses,
          pause_threshold_ms: safePauseThreshold,
          remove_filler_words: projectRemoveFillerWords,
          filtered_words: normalizedFilteredWords,
          apply_to_existing: true,
        }),
      });
      if (!response.ok) {
        alert(await buildSupportError(response, "Failed to apply settings"));
        return;
      }
      await fetchTaskStatus();
    } finally {
      setIsApplyingSettings(false);
    }
  };

  const handleExportClip = async (clipId: string, fallbackFilename: string) => {
    if (!session?.user?.id || !task?.id) return;

    const response = await fetch(`${taskApiUrl}/${task.id}/clips/${clipId}/export?preset=${exportPreset}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      alert(await buildSupportError(response, "Failed to export clip"));
      return;
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = `${fallbackFilename.replace(/\.mp4$/i, "")}_${exportPreset}.mp4`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
  };

  const handleDownloadClip = (clip: Clip) => {
    if (exportPreset === "original") {
      const link = document.createElement("a");
      link.href = clip.video_url.startsWith("/api/") ? clip.video_url : `/api${clip.video_url}`;
      link.download = clip.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      return;
    }
    void handleExportClip(clip.id, clip.filename);
  };

  const handleCancelTask = async () => {
    if (!task?.id) return;
    await fetch(`${taskApiUrl}/${task.id}/cancel`, { method: "POST" });
    await fetchTaskStatus();
  };

  const handleResumeTask = async () => {
    if (!task?.id) return;
    await fetch(`${taskApiUrl}/${task.id}/resume`, { method: "POST" });
    await fetchTaskStatus();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background p-4">
        <div className="max-w-6xl mx-auto">
          <div className="mb-6">
            <Skeleton className="h-8 w-48 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <div className="grid gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardContent className="p-6">
                  <Skeleton className="h-48 w-full mb-4" />
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4" />
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background p-4">
        <div className="max-w-6xl mx-auto">
          <Alert>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
          <Link href="/" className="mt-4 inline-block">
            <Button variant="outline">
              <ArrowLeft className="w-4 h-4" />
              Back to Home
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      {task && (
        <TaskHeader
          task={task}
          clips={clips}
          isEditing={isEditing}
          editedTitle={editedTitle}
          onEditTitleChange={setEditedTitle}
          onStartEdit={() => { setIsEditing(true); setEditedTitle(task.source_title); }}
          onSaveEdit={handleEditTitle}
          onCancelEdit={() => { setIsEditing(false); setEditedTitle(task.source_title); }}
          onDeleteClick={() => setShowDeleteDialog(true)}
          onCancelTask={handleCancelTask}
          onResumeTask={handleResumeTask}
        />
      )}

      <div className="max-w-6xl mx-auto px-4 py-8">
        {task?.status === "processing" || task?.status === "queued" ? (
          <ProcessingState
            status={task.status}
            progress={progress}
            progressMessage={progressMessage}
            clips={clips}
            subProgress={subProgress}
            subMessage={subMessage}
            progressMetadata={progressMetadata}
          />
        ) : !task ? (
          <div className="flex flex-col items-center justify-center min-h-[50vh] py-16">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 bg-muted rounded-full animate-[pulse_1.4s_ease-in-out_infinite]" />
              <span className="w-2 h-2 bg-muted rounded-full animate-[pulse_1.4s_ease-in-out_0.2s_infinite]" />
              <span className="w-2 h-2 bg-muted rounded-full animate-[pulse_1.4s_ease-in-out_0.4s_infinite]" />
            </div>
          </div>
        ) : task.status === "error" ? (
          <Card>
            <CardContent className="p-8 text-center">
              <div className="text-destructive mb-4">
                <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                <h2 className="text-xl font-semibold">Processing Failed</h2>
              </div>
              <p className="text-muted-foreground mb-2">{task?.progress_message || "There was an error processing your video."}</p>
              {task?.error_code && (
                <div className="mb-4 flex items-center justify-center gap-2">
                  <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono text-muted-foreground">{task.error_code}</code>
                  <button onClick={() => navigator.clipboard.writeText(task.error_code!)} className="text-xs text-primary hover:underline">Copy</button>
                </div>
              )}
              <div className="flex items-center justify-center gap-2">
                <Link href="/"><Button variant="outline" size="sm"><ArrowLeft className="w-4 h-4" /> Back to Home</Button></Link>
                <Button size="sm" onClick={() => { fetch(`/api/tasks/${task?.id}/cancel`, { method: "POST" }).then(() => { window.location.href = "/"; }); }}>
                  Dismiss & Retry
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : clips.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              {task?.status === "completed" ? (
                <>
                  <div className="text-yellow-600 mb-4">
                    <AlertCircle className="w-12 h-12 mx-auto mb-2" />
                    <h2 className="text-xl font-semibold">No Clips Generated</h2>
                  </div>
                  <p className="text-muted-foreground mb-4">The task completed but no clips were generated. The video may not have had suitable content for clipping.</p>
                  <Link href="/"><Button><ArrowLeft className="w-4 h-4" /> Try Another Video</Button></Link>
                </>
              ) : (
                <>
                  <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Clock className="w-8 h-8 text-blue-500 animate-pulse" />
                  </div>
                  <h2 className="text-xl font-semibold text-foreground mb-2">Still Generating...</h2>
                  <p className="text-muted-foreground">Your clips are being generated. This page will refresh automatically when they&apos;re ready.</p>
                </>
              )}
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-6">
            <div className="flex items-center justify-between">
              <Button variant="outline" size="sm" onClick={() => setSettingsSheetOpen(true)}>
                <Settings2 className="w-4 h-4" />
                Project Settings
              </Button>
              {selectedClipIds.length >= 2 && (
                <Button variant="outline" size="sm" onClick={handleMergeClips}>
                  <GitMerge className="w-4 h-4" />
                  Merge Selected ({selectedClipIds.length})
                </Button>
              )}
            </div>

            <ProjectSettingsSheet
              open={settingsSheetOpen}
              onOpenChange={setSettingsSheetOpen}
              fontFamily={projectFontFamily}
              fontSize={projectFontSize}
              fontColor={projectFontColor}
              captionTemplate={projectCaptionTemplate}
              includeBroll={projectIncludeBroll}
              cutLongPauses={projectCutLongPauses}
              pauseThresholdMs={projectPauseThresholdMs}
              removeFillerWords={projectRemoveFillerWords}
              filteredWords={projectFilteredWords}
              availableFonts={availableFonts}
              availableTemplates={availableTemplates}
              isApplying={isApplyingSettings}
              onFontFamilyChange={setProjectFontFamily}
              onFontSizeChange={setProjectFontSize}
              onFontColorChange={setProjectFontColor}
              onCaptionTemplateChange={setProjectCaptionTemplate}
              onIncludeBrollChange={setProjectIncludeBroll}
              onCutLongPausesChange={setProjectCutLongPauses}
              onPauseThresholdMsChange={setProjectPauseThresholdMs}
              onRemoveFillerWordsChange={setProjectRemoveFillerWords}
              onFilteredWordsChange={setProjectFilteredWords}
              onApply={() => { handleApplyProjectSettings(); setSettingsSheetOpen(false); }}
            />

            {clips.map((clip) => (
              <ClipCard
                key={clip.id}
                clip={clip}
                exportPreset={exportPreset}
                editingClipId={editingClipId}
                startOffset={startOffset}
                endOffset={endOffset}
                splitTime={splitTime}
                captionText={captionText}
                captionPosition={captionPosition}
                highlightWords={highlightWords}
                selected={selectedClipIds.includes(clip.id)}
                onToggleSelection={() => handleToggleClipSelection(clip.id)}
                onDownload={() => handleDownloadClip(clip)}
                onExportPresetChange={setExportPreset}
                onEdit={() => {
                  setEditingClipId(editingClipId === clip.id ? null : clip.id);
                  setCaptionText(clip.text || "");
                }}
                onYoutube={() => setYoutubeModalClip(clip)}
                onDelete={() => setDeletingClipId(clip.id)}
                onTrim={() => handleTrimClip(clip.id)}
                onSplit={() => handleSplitClip(clip.id)}
                onRegenerate={() => handleTrimClip(clip.id)}
                onUpdateCaptions={() => handleUpdateCaptions(clip.id)}
                onStartOffsetChange={setStartOffset}
                onEndOffsetChange={setEndOffset}
                onSplitTimeChange={setSplitTime}
                onCaptionTextChange={setCaptionText}
                onCaptionPositionChange={setCaptionPosition}
                onHighlightWordsChange={setHighlightWords}
              />
            ))}
          </div>
        )}
      </div>

      <YouTubeUploadModal
        clip={youtubeModalClip}
        task={task}
        apiUrl={apiUrl}
        onClose={() => setYoutubeModalClip(null)}
      />

      <DeleteConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        onConfirm={handleDeleteTask}
        loading={isDeleting}
        title="Delete Generation"
        description="Are you sure you want to delete this generation? This will permanently delete all clips and cannot be undone."
      />

      <DeleteConfirmDialog
        open={!!deletingClipId}
        onOpenChange={(open) => !open && setDeletingClipId(null)}
        onConfirm={() => deletingClipId && handleDeleteClip(deletingClipId)}
        title="Delete Clip"
        description="Are you sure you want to delete this clip? This action cannot be undone."
      />
    </div>
  );
}
