"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useSession } from "@/lib/auth-client";
import { isPaidBillingPlan } from "@/lib/billing-plans";
import { track } from "@/lib/datafast";
import { formatSupportMessage, parseApiError } from "@/lib/api-error";
import Link from "next/link";
import {
  ArrowRight, Youtube, CheckCircle, AlertCircle, Loader2,
  Palette, Type, Paintbrush, Film, Sparkles, Upload, Monitor,
} from "lucide-react";
import { isLandingOnlyModeEnabled } from "@/lib/app-flags";
import LandingPage from "@/components/landing-page";
import { HomeHeader } from "@/components/tasks/home-header";
import { PhonePreview } from "@/components/tasks/phone-preview";
import { ProcessingProgress } from "@/components/tasks/processing-progress";

interface LatestTask {
  id: string;
  source_title: string;
  source_type: string;
  status: string;
  clips_count: number;
  created_at: string;
}

interface BillingSummary {
  monetization_enabled: boolean;
  plan: string;
  subscription_status: string;
  usage_count: number;
  usage_limit: number | null;
  remaining: number | null;
  can_create_task: boolean;
  upgrade_required: boolean;
  reason: string | null;
}

interface FontOption {
  name: string;
  display_name: string;
  format?: string;
}

type OutputFormat = "vertical" | "vertical_pan" | "vertical_split" | "vertical_blur" | "original";

const MAX_VIDEO_UPLOAD_BYTES = 1_000_000_000;

interface DirectUploadAuthorization {
  directUpload: true;
  uploadUrl: string;
  headers: Record<string, string>;
}

interface ProxyUploadAuthorization {
  directUpload: false;
  reason: "signed_backend_auth_required";
}

type UploadAuthorization = DirectUploadAuthorization | ProxyUploadAuthorization;

const extractYouTubeVideoId = (value: string): string | null => {
  const input = value.trim();
  if (!input) return null;

  try {
    const parsed = new URL(input);
    const host = parsed.hostname.replace(/^www\./, "");

    if (host === "youtu.be") {
      const id = parsed.pathname.split("/").filter(Boolean)[0];
      return id && id.length === 11 ? id : null;
    }

    if (host === "youtube.com" || host === "m.youtube.com" || host === "music.youtube.com") {
      const fromSearch = parsed.searchParams.get("v");
      if (fromSearch && fromSearch.length === 11) return fromSearch;

      const pathParts = parsed.pathname.split("/").filter(Boolean);
      const embedId = pathParts[0] === "embed" ? pathParts[1] : null;
      if (embedId && embedId.length === 11) return embedId;
    }
  } catch {
    return null;
  }

  return null;
};

const getYouTubeThumbnailUrl = (value: string): string | null => {
  const videoId = extractYouTubeVideoId(value);
  return videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null;
};

async function requestUploadAuthorization(): Promise<UploadAuthorization> {
  const response = await fetch("/api/upload/authorization", {
    method: "POST",
    cache: "no-store",
  });

  if (!response.ok) {
    const uploadError = await parseApiError(
      response,
      `Upload authorization error: ${response.status}`,
    );
    throw new Error(formatSupportMessage(uploadError));
  }

  return response.json() as Promise<UploadAuthorization>;
}

async function uploadVideoFile(file: File): Promise<string> {
  if (file.size > MAX_VIDEO_UPLOAD_BYTES) {
    throw new Error("Uploaded file is too large. Please upload a video under 1 GB.");
  }

  const uploadAuthorization = await requestUploadAuthorization();
  if (!uploadAuthorization.directUpload) {
    return uploadVideoFileViaProxy(file);
  }

  const formData = new FormData();
  formData.append("video", file);

  const uploadResponse = await fetch(uploadAuthorization.uploadUrl, {
    method: "POST",
    headers: uploadAuthorization.headers,
    body: formData,
  });

  if (!uploadResponse.ok) {
    const fallbackMessage =
      uploadResponse.status === 413
        ? "Uploaded file is too large. Please upload a video under 1 GB."
        : `Upload error: ${uploadResponse.status}`;
    const uploadError = await parseApiError(uploadResponse, fallbackMessage);
    throw new Error(formatSupportMessage(uploadError));
  }

  const uploadResult = await uploadResponse.json();
  if (typeof uploadResult.video_path !== "string" || !uploadResult.video_path) {
    throw new Error("Upload finished without a video path. Please try again.");
  }

  return uploadResult.video_path;
}

async function uploadVideoFileViaProxy(file: File): Promise<string> {
  const formData = new FormData();
  formData.append("video", file);

  const uploadResponse = await fetch("/api/upload", {
    method: "POST",
    body: formData,
  });

  if (!uploadResponse.ok) {
    const fallbackMessage =
      uploadResponse.status === 413
        ? "Uploaded file is too large. Please upload a video under 1 GB."
        : `Upload error: ${uploadResponse.status}`;
    const uploadError = await parseApiError(uploadResponse, fallbackMessage);
    throw new Error(formatSupportMessage(uploadError));
  }

  const uploadResult = await uploadResponse.json();
  if (typeof uploadResult.video_path !== "string" || !uploadResult.video_path) {
    throw new Error("Upload finished without a video path. Please try again.");
  }

  return uploadResult.video_path;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [currentStep, setCurrentStep] = useState("");
  const [sourceType, setSourceType] = useState<"youtube" | "upload">("youtube");
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourceTitle, setSourceTitle] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const { data: session, isPending } = useSession();
  const isAdmin = Boolean((session?.user as { is_admin?: boolean } | undefined)?.is_admin);

  const [fontFamily, setFontFamily] = useState("TikTokSans-Regular");
  const [fontSize, setFontSize] = useState(48);
  const [fontColor, setFontColor] = useState("#FFFFFF");
  const [availableFonts, setAvailableFonts] = useState<FontOption[]>([]);
  const [showAdvancedOptions, setShowAdvancedOptions] = useState(true);
  const [fontSearch, setFontSearch] = useState("");
  const [fontLoadError, setFontLoadError] = useState<string | null>(null);
  const [isUploadingFont, setIsUploadingFont] = useState(false);
  const fontUploadInputRef = useRef<HTMLInputElement | null>(null);

  const [captionTemplate, setCaptionTemplate] = useState("default");
  const [availableTemplates, setAvailableTemplates] = useState<Array<{ id: string, name: string, description: string, animation: string, font_family?: string, font_size?: number, font_color?: string }>>([]);
  const [includeBroll, setIncludeBroll] = useState(false);
  const [brollAvailable, setBrollAvailable] = useState(false);
  const [outputFormat, setOutputFormat] = useState<OutputFormat>("vertical");
  const [addSubtitles, setAddSubtitles] = useState(true);
  const [cutLongPauses, setCutLongPauses] = useState(false);
  const [pauseThresholdMs, setPauseThresholdMs] = useState("900");
  const [removeFillerWords, setRemoveFillerWords] = useState(false);
  const [filteredWords, setFilteredWords] = useState("");

  const [latestTask, setLatestTask] = useState<LatestTask | null>(null);
  const [isLoadingLatest, setIsLoadingLatest] = useState(false);
  const [billingSummary, setBillingSummary] = useState<BillingSummary | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const taskApiUrl = "/api/tasks";
  const youtubeThumbnailUrl = sourceType === "youtube" ? getYouTubeThumbnailUrl(url) : null;

  const refreshFonts = useCallback(async () => {
    try {
      setFontLoadError(null);
      const response = await fetch("/api/fonts", { cache: "no-store" });
      if (!response.ok) throw new Error(`Failed to load fonts (${response.status})`);

      const data = await response.json();
      const fonts: FontOption[] = data.fonts || [];
      setAvailableFonts(fonts);

      const fontFaceStyles = fonts.map((font) => {
        const format = font.format === "otf" ? "opentype" : "truetype";
        return `
          @font-face {
            font-family: '${font.name}';
            src: url('/api/fonts/${font.name}') format('${format}');
            font-weight: normal;
            font-style: normal;
          }
        `;
      }).join("\n");

      const styleElement = document.createElement("style");
      styleElement.id = "custom-fonts";
      styleElement.innerHTML = fontFaceStyles;

      const existingStyle = document.getElementById("custom-fonts");
      if (existingStyle) existingStyle.remove();

      document.head.appendChild(styleElement);
    } catch (error) {
      console.error("Failed to load fonts:", error);
      setFontLoadError("Could not load fonts right now.");
    }
  }, []);

  useEffect(() => { void refreshFonts(); }, [refreshFonts]);

  useEffect(() => {
    const loadTemplates = async () => {
      try {
        const response = await fetch(`${apiUrl}/caption-templates`);
        if (response.ok) {
          const data = await response.json();
          setAvailableTemplates(data.templates || []);
        }
      } catch { /* ignore */ }
    };

    const checkBrollStatus = async () => {
      try {
        const response = await fetch(`${apiUrl}/broll/status`);
        if (response.ok) {
          const data = await response.json();
          setBrollAvailable(data.configured || false);
        }
      } catch { /* ignore */ }
    };

    loadTemplates();
    checkBrollStatus();
  }, [apiUrl]);

  useEffect(() => {
    const loadUserPreferences = async () => {
      if (!session?.user?.id) return;
      try {
        const response = await fetch('/api/preferences');
        if (response.ok) {
          const data = await response.json();
          setFontFamily(data.fontFamily || "TikTokSans-Regular");
          setFontSize(data.fontSize || 48);
          setFontColor(data.fontColor || "#FFFFFF");
        }
      } catch { /* ignore */ }
    };
    loadUserPreferences();
  }, [session?.user?.id]);

  useEffect(() => {
    const fetchLatestTask = async () => {
      if (!session?.user?.id) return;
      try {
        setIsLoadingLatest(true);
        const response = await fetch(`${taskApiUrl}/`, { cache: "no-store" });
        if (response.ok) {
          const data = await response.json();
          if (data.tasks && data.tasks.length > 0) {
            setLatestTask(data.tasks[0]);
          }
        }
      } catch { /* ignore */ }
      finally { setIsLoadingLatest(false); }
    };
    fetchLatestTask();
  }, [session?.user?.id, taskApiUrl]);

  useEffect(() => {
    const fetchBillingSummary = async () => {
      if (!session?.user?.id) return;
      try {
        const response = await fetch("/api/tasks/billing-summary", { cache: "no-store" });
        if (response.ok) {
          setBillingSummary(await response.json());
        }
      } catch { /* ignore */ }
    };
    fetchBillingSummary();
  }, [session?.user?.id, apiUrl]);

  const fileRef = useRef<File | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    fileRef.current = file;
    setFileName(file ? file.name : null);
  };

  const handleTemplateChange = (templateId: string) => {
    setCaptionTemplate(templateId);
    const selectedTemplate = availableTemplates.find((template) => template.id === templateId);
    if (!selectedTemplate) return;
    if (selectedTemplate.font_family) setFontFamily(selectedTemplate.font_family);
    if (typeof selectedTemplate.font_size === "number") setFontSize(selectedTemplate.font_size);
    if (selectedTemplate.font_color) setFontColor(selectedTemplate.font_color);
  };

  const handleFontUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    const isSupported = file.name.toLowerCase().endsWith(".ttf") || file.name.toLowerCase().endsWith(".otf");
    if (!isSupported) { setError("Only .ttf and .otf files are supported for custom fonts."); return; }

    try {
      setIsUploadingFont(true);
      setError(null);
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("/api/fonts/upload", { method: "POST", body: formData });
      if (!response.ok) {
        const parsed = await parseApiError(response, "Failed to upload font");
        setError(formatSupportMessage(parsed));
        return;
      }
      const data = await response.json();
      if (data?.font?.name) setFontFamily(data.font.name);
      await refreshFonts();
    } catch {
      setError("Failed to upload font. Please try again.");
    } finally { setIsUploadingFont(false); }
  };

  const filteredFonts = availableFonts.filter((font) => {
    const keyword = fontSearch.toLowerCase().trim();
    if (!keyword) return true;
    return font.display_name.toLowerCase().includes(keyword) || font.name.toLowerCase().includes(keyword);
  });

  const canUploadCustomFonts =
    !billingSummary?.monetization_enabled ||
    (isPaidBillingPlan(billingSummary.plan) && ["active", "trialing"].includes(billingSummary.subscription_status));
  const generationRequiresUpgrade =
    Boolean(billingSummary?.monetization_enabled && !billingSummary.can_create_task);
  const generationGateMessage =
    billingSummary?.reason || "Choose a paid plan to process videos.";
  const generationControlsDisabled = isLoading || generationRequiresUpgrade;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (sourceType === "upload" && !fileRef.current) return;
    if (sourceType === "youtube" && !url.trim()) return;
    if (!session?.user?.id) return;
    if (generationRequiresUpgrade) { setError(generationGateMessage); return; }

    setIsLoading(true);
    setProgress(0);
    setError(null);
    setStatusMessage("");
    setCurrentStep("");
    setSourceTitle(null);

    const normalizedColor = /^#[0-9A-Fa-f]{6}$/.test(fontColor) ? fontColor : "#FFFFFF";

    try {
      let videoUrl = url;
      const normalizedPauseThreshold = Number.isFinite(Number(pauseThresholdMs))
        ? Math.max(250, Math.min(3000, Math.round(Number(pauseThresholdMs))))
        : 900;
      const normalizedFilteredWords = filteredWords
        .split(",").map((word) => word.trim().toLowerCase()).filter(Boolean);

      if (sourceType === "upload" && fileRef.current) {
        setStatusMessage("Uploading video file...");
        setProgress(5);
        videoUrl = await uploadVideoFile(fileRef.current);
      }

      const startResponse = await fetch("/api/tasks/create", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source: { url: videoUrl, title: null },
          font_options: { font_family: fontFamily, font_size: fontSize, font_color: normalizedColor },
          caption_template: captionTemplate,
          include_broll: includeBroll,
          processing_mode: "fast",
          output_format: outputFormat,
          add_subtitles: addSubtitles,
          cut_long_pauses: cutLongPauses,
          pause_threshold_ms: normalizedPauseThreshold,
          remove_filler_words: removeFillerWords,
          filtered_words: normalizedFilteredWords,
        }),
      });

      if (!startResponse.ok) {
        const startError = await parseApiError(startResponse, `API error: ${startResponse.status}`);
        throw new Error(formatSupportMessage(startError));
      }

      const startResult = await startResponse.json();
      track("task_created", {
        source_type: sourceType,
        caption_template: captionTemplate,
        include_broll: includeBroll,
        output_format: outputFormat,
        add_subtitles: addSubtitles,
        cut_long_pauses: cutLongPauses,
        pause_threshold_ms: normalizedPauseThreshold,
        remove_filler_words: removeFillerWords,
        filtered_words: normalizedFilteredWords,
        processing_mode: "fast",
      });
      window.location.href = `/tasks/${startResult.task_id}`;
    } catch (error) {
      console.error('Error processing video:', error);
      setError(error instanceof Error ? error.message : 'Failed to process video. Please try again.');
    } finally {
      setIsLoading(false);
      setProgress(0);
      setStatusMessage("");
      setCurrentStep("");
      setFileName(null);
      fileRef.current = null;
      setUrl("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  if (isPending) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="space-y-4">
          <Skeleton className="h-4 w-32 mx-auto" />
          <Skeleton className="h-4 w-48 mx-auto" />
          <Skeleton className="h-4 w-24 mx-auto" />
        </div>
      </div>
    );
  }

  if (isLandingOnlyModeEnabled || !session?.user) {
    return <LandingPage />;
  }

  return (
    <div className="min-h-screen bg-background">
      <HomeHeader billingSummary={billingSummary} isAdmin={isAdmin} />

      <div className="max-w-6xl mx-auto px-6 py-10">
        {/* Latest Generation Banner */}
        {latestTask && (
          <Link href={`/tasks/${latestTask.id}`} className="block mb-8">
            <div className="flex items-center justify-between p-4 rounded-xl border border-border bg-muted/50 hover:bg-muted transition-colors group">
              <div className="flex items-center gap-4 min-w-0">
                <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary flex items-center justify-center">
                  <Film className="w-5 h-5 text-white" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{latestTask.source_title}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                    <span className="capitalize">{latestTask.source_type}</span>
                    <span>&middot;</span>
                    <span>{new Date(latestTask.created_at).toLocaleDateString()}</span>
                    <span>&middot;</span>
                    <span>{latestTask.clips_count} {latestTask.clips_count === 1 ? "clip" : "clips"}</span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                {latestTask.status === "completed" ? (
                  <Badge className="bg-green-100 text-green-800 text-xs"><CheckCircle className="w-3 h-3 mr-1" /> Completed</Badge>
                ) : latestTask.status === "processing" ? (
                  <Badge className="bg-blue-100 text-blue-800 text-xs"><Loader2 className="w-3 h-3 animate-spin" /> Processing</Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">{latestTask.status}</Badge>
                )}
                <ArrowRight className="w-4 h-4 text-muted-foreground group-hover:text-muted-foreground transition-colors" />
              </div>
            </div>
          </Link>
        )}

        {isLoadingLatest && (
          <div className="mb-8 p-4 rounded-xl border border-border">
            <div className="flex items-center gap-4">
              <Skeleton className="w-10 h-10 rounded-lg" />
              <div><Skeleton className="h-4 w-48 mb-1.5" /><Skeleton className="h-3 w-32" /></div>
            </div>
          </div>
        )}

        {/* Two Column Layout */}
        <div className="flex flex-col lg:flex-row gap-10 items-start">
          {/* Left Column — Form */}
          <div className="flex-1 min-w-0">
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-foreground mb-2">Create New Clip</h2>
              <p className="text-muted-foreground">
                {generationRequiresUpgrade
                  ? "Video processing is available on paid plans."
                  : "Paste a YouTube link or upload a video — AI handles the rest."}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {generationRequiresUpgrade && (
                <Alert className="border-amber-200 bg-amber-50">
                  <AlertCircle className="h-4 w-4 text-amber-600" />
                  <AlertDescription className="text-sm text-amber-900">
                    <span className="font-medium">{generationGateMessage}</span>{" "}
                    Free accounts can browse ArioClip, but video generation requires a paid plan.
                    <Link href="/settings" className="ml-1 font-semibold underline underline-offset-2">Upgrade in settings</Link>.
                  </AlertDescription>
                </Alert>
              )}

              {/* Source Type Tabs */}
              <div className="space-y-3">
                <div className="flex gap-2">
                  <button type="button" onClick={() => { setSourceType("youtube"); setFileName(null); fileRef.current = null; if (fileInputRef.current) fileInputRef.current.value = ""; }}
                    disabled={generationControlsDisabled}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      sourceType === "youtube" ? "bg-primary text-primary-foreground shadow-sm" : "bg-muted text-muted-foreground hover:bg-muted"
                    }`}>
                    <Youtube className="w-4 h-4" /> YouTube URL
                  </button>
                  <button type="button" onClick={() => setSourceType("upload")} disabled={generationControlsDisabled}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      sourceType === "upload" ? "bg-primary text-primary-foreground shadow-sm" : "bg-muted text-muted-foreground hover:bg-muted"
                    }`}>
                    <Upload className="w-4 h-4" /> Upload Video
                  </button>
                </div>

                {sourceType === "youtube" ? (
                  <div className="relative">
                    <Youtube className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
                    <Input type="url" placeholder="https://www.youtube.com/watch?v=..."
                      value={url} onChange={(e) => setUrl(e.target.value)}
                      disabled={generationControlsDisabled}
                      className="h-14 pl-12 text-base rounded-xl border-border focus:border-border placeholder:text-muted-foreground" />
                  </div>
                ) : (
                  <div className="relative border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-border transition-colors cursor-pointer"
                    onClick={() => !generationControlsDisabled && fileInputRef.current?.click()}>
                    <input type="file" accept="video/*" ref={fileInputRef} onChange={handleFileChange} disabled={generationControlsDisabled} className="hidden" />
                    <Upload className="w-8 h-8 text-muted-foreground mx-auto mb-3" />
                    {fileName ? (
                      <p className="text-sm font-medium text-foreground">{fileName}</p>
                    ) : (
                      <>
                        <p className="text-sm font-medium text-muted-foreground">Drop a video file here or click to browse</p>
                        <p className="text-xs text-muted-foreground mt-1">MP4, MOV, AVI up to 500MB</p>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Caption & Style Section */}
              <Card className="border-border">
                <CardContent className="px-4 pt-0 pb-2.5 space-y-2.5">
                  <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                    <Sparkles className="w-4 h-4" />
                    Style & Captions
                  </div>

                  <div className="space-y-2">
                    <label className="text-sm text-muted-foreground">Caption Style</label>
                    <Select value={captionTemplate} onValueChange={handleTemplateChange} disabled={generationControlsDisabled}>
                      <SelectTrigger className="w-full h-11">
                        <SelectValue>{availableTemplates.find(t => t.id === captionTemplate)?.name || "Select style"}</SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {availableTemplates.length > 0 ? (
                          availableTemplates.map((template) => (
                            <SelectItem key={template.id} value={template.id} className="py-2">
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{template.name}</span>
                                {template.animation && template.animation !== "none" && (
                                  <span className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-primary/10 text-primary uppercase tracking-wider">
                                    {template.animation.replace(/_/g, " ")}
                                  </span>
                                )}
                              </div>
                              <span className="text-xs text-muted-foreground block">{template.description}</span>
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="default">Default</SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                  </div>

                  {brollAvailable && (
                    <div className="flex items-center justify-between p-3 border rounded-lg bg-muted">
                      <div className="flex items-center gap-3">
                        <Film className="w-4 h-4 text-purple-500" />
                        <div>
                          <h3 className="text-sm font-medium text-foreground">AI B-Roll</h3>
                          <p className="text-xs text-muted-foreground">Auto-add stock footage from Pexels</p>
                        </div>
                      </div>
                      <Switch checked={includeBroll} onCheckedChange={setIncludeBroll} disabled={generationControlsDisabled} />
                    </div>
                  )}

                  <div className="flex items-center justify-between gap-4 p-3 border rounded-lg bg-muted">
                    <div className="flex min-w-0 items-center gap-3">
                      <Monitor className="w-4 h-4 text-blue-500" />
                      <div>
                        <h3 className="text-sm font-medium text-foreground">Framing</h3>
                        <p className="text-xs text-muted-foreground">Choose how clips are reframed for social video</p>
                      </div>
                    </div>
                    <Select value={outputFormat} onValueChange={(value) => setOutputFormat(value as OutputFormat)} disabled={generationControlsDisabled}>
                      <SelectTrigger className="w-[180px] bg-background"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="vertical">Auto 9:16</SelectItem>
                        <SelectItem value="vertical_pan">Speaker pan</SelectItem>
                        <SelectItem value="vertical_split">Split-screen</SelectItem>
                        <SelectItem value="vertical_blur">Blur background</SelectItem>
                        <SelectItem value="original">Original</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-center justify-between p-3 border rounded-lg bg-muted">
                    <div className="flex items-center gap-3">
                      <Type className="w-4 h-4 text-emerald-500" />
                      <div>
                        <h3 className="text-sm font-medium text-foreground">Add subtitles</h3>
                        <p className="text-xs text-muted-foreground">Burn captions onto clips (disable for faster processing)</p>
                      </div>
                    </div>
                    <Switch checked={addSubtitles} onCheckedChange={setAddSubtitles} disabled={generationControlsDisabled} />
                  </div>

                  <div className="rounded-lg border bg-muted p-3 space-y-3">
                    <div>
                      <h3 className="text-sm font-medium text-foreground">Clip cleanup</h3>
                      <p className="text-xs text-muted-foreground">Remove dead air and common filler phrases while rendering.</p>
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-foreground">Cut long pauses</div>
                        <div className="text-xs text-muted-foreground">Split out silence gaps longer than your threshold.</div>
                      </div>
                      <Switch checked={cutLongPauses} onCheckedChange={setCutLongPauses} disabled={generationControlsDisabled} />
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Pause threshold (ms)</label>
                      <Input type="number" min={250} max={3000} step={50}
                        value={pauseThresholdMs} onChange={(e) => setPauseThresholdMs(e.target.value)}
                        disabled={generationControlsDisabled || !cutLongPauses} placeholder="900" />
                    </div>

                    <div className="flex items-center justify-between">
                      <div>
                        <div className="text-sm font-medium text-foreground">Remove filler words</div>
                        <div className="text-xs text-muted-foreground">Uses a safe default list like &ldquo;um&rdquo;, &ldquo;uh&rdquo;, and &ldquo;you know&rdquo;.</div>
                      </div>
                      <Switch checked={removeFillerWords} onCheckedChange={setRemoveFillerWords} disabled={generationControlsDisabled} />
                    </div>

                    <div className="space-y-1.5">
                      <label className="text-xs font-medium text-muted-foreground">Extra filtered words or phrases</label>
                      <Input value={filteredWords} onChange={(e) => setFilteredWords(e.target.value)}
                        disabled={generationControlsDisabled} placeholder="basically, literally, to be honest" />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Font Customization Section */}
              <div className={`transition-all duration-500 ease-in-out overflow-hidden ${
                addSubtitles ? "max-h-[800px] opacity-100" : "max-h-0 opacity-0 pointer-events-none"
              }`}>
                <Card className="border-border">
                  <CardContent className="px-4 pt-0 pb-2.5 space-y-2.5">
                    <div className="flex items-center justify-between cursor-pointer"
                      onClick={() => setShowAdvancedOptions(!showAdvancedOptions)}>
                      <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                        <Paintbrush className="w-4 h-4" />
                        Font Customization
                      </div>
                      <button type="button" className="text-xs text-muted-foreground hover:text-muted-foreground transition-colors">
                        {showAdvancedOptions ? "Hide" : "Show"}
                      </button>
                    </div>

                    {showAdvancedOptions && (
                      <div className="space-y-5 pt-1">
                        <div className="space-y-2">
                          <label className="text-sm text-muted-foreground flex items-center gap-2">
                            <Type className="w-3.5 h-3.5" /> Font Family
                          </label>
                          <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                            <span>{availableFonts.length} font{availableFonts.length === 1 ? "" : "s"} available</span>
                            <input ref={fontUploadInputRef} type="file" accept=".ttf,.otf" onChange={handleFontUpload} className="hidden" />
                            <Button type="button" variant="outline" size="sm"
                              disabled={generationControlsDisabled || isUploadingFont || !canUploadCustomFonts}
                              onClick={() => fontUploadInputRef.current?.click()}>
                              {isUploadingFont ? "Uploading..." : "Upload Font"}
                            </Button>
                          </div>
                          {!canUploadCustomFonts && <p className="text-xs text-amber-700">Custom font upload is available on paid plans.</p>}
                          <Input type="text" value={fontSearch} onChange={(e) => setFontSearch(e.target.value)}
                            placeholder="Search fonts" disabled={generationControlsDisabled} />
                          <Select value={fontFamily} onValueChange={setFontFamily} disabled={generationControlsDisabled}>
                            <SelectTrigger className="w-full"><SelectValue placeholder="Select font" /></SelectTrigger>
                            <SelectContent>
                              {filteredFonts.map((font) => (
                                <SelectItem key={font.name} value={font.name}>
                                  <span style={{ fontFamily: `'${font.name}', system-ui, sans-serif` }}>{font.display_name}</span>
                                </SelectItem>
                              ))}
                              {availableFonts.length === 0 && <SelectItem value="TikTokSans-Regular">TikTok Sans Regular</SelectItem>}
                              {availableFonts.length > 0 && filteredFonts.length === 0 && <SelectItem value="__no_match__" disabled>No fonts match your search</SelectItem>}
                            </SelectContent>
                          </Select>
                          {fontLoadError && <p className="text-xs text-amber-700">{fontLoadError}</p>}
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-2">
                            <label className="text-sm text-muted-foreground">Size: {fontSize}px</label>
                            <div className="px-1">
                              <Slider value={[fontSize]} onValueChange={(value) => setFontSize(value[0])}
                                max={96} min={24} step={2} disabled={generationControlsDisabled} className="w-full" />
                            </div>
                            <div className="flex justify-between text-xs text-muted-foreground"><span>24px</span><span>96px</span></div>
                          </div>

                          <div className="space-y-2">
                            <label className="text-sm text-muted-foreground flex items-center gap-1.5">
                              <Palette className="w-3.5 h-3.5" /> Color
                            </label>
                            <div className="flex items-center gap-2">
                              <input type="color" value={fontColor} onChange={(e) => setFontColor(e.target.value)}
                                disabled={generationControlsDisabled}
                                className="w-10 h-8 rounded border border-border cursor-pointer disabled:cursor-not-allowed" />
                              <Input type="text" value={fontColor} onChange={(e) => setFontColor(e.target.value)}
                                disabled={generationControlsDisabled} placeholder="#FFFFFF"
                                className="flex-1 h-8 text-xs" pattern="^#[0-9A-Fa-f]{6}$" />
                            </div>
                            <div className="flex gap-1.5 mt-1">
                              {["#FFFFFF", "#000000", "#FFD700", "#FF6B6B", "#4ECDC4", "#45B7D1"].map((color) => (
                                <button key={color} type="button" onClick={() => setFontColor(color)}
                                  disabled={generationControlsDisabled}
                                  className="w-5 h-5 rounded border-2 border-border cursor-pointer hover:scale-110 transition-transform disabled:cursor-not-allowed"
                                  style={{ backgroundColor: color }} title={color} />
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {isLoading && (
                <ProcessingProgress
                  progress={progress}
                  currentStep={currentStep}
                  statusMessage={statusMessage}
                  sourceTitle={sourceTitle}
                />
              )}

              {error && (
                <Alert className="border-red-200 bg-red-50">
                  <AlertCircle className="h-4 w-4 text-red-500" />
                  <AlertDescription className="text-sm text-red-700">{error}</AlertDescription>
                </Alert>
              )}

              <p className="text-xs text-muted-foreground">
                Completion emails use your user preference in{" "}
                <Link href="/settings" className="font-medium text-muted-foreground underline underline-offset-2">Settings</Link>.
              </p>

              <Button type="submit" className="w-full h-12 text-base rounded-xl"
                disabled={(sourceType === "youtube" && !url.trim()) || (sourceType === "upload" && !fileRef.current) || generationRequiresUpgrade || isLoading}>
                {isLoading ? "Processing..." : generationRequiresUpgrade ? "Choose a Paid Plan" : "Process Video"}
              </Button>
            </form>
          </div>

          {/* Right Column — Phone Preview */}
          <div className={`hidden lg:block flex-shrink-0 overflow-hidden transition-all duration-500 ease-in-out ${
            sourceType === "upload" ? "w-0 opacity-0" : "w-[340px] opacity-100"
          }`}>
            <div className={`w-[340px] transition-all duration-500 ease-in-out ${
              sourceType === "upload" ? "translate-x-6 scale-[0.97] opacity-0" : "translate-x-0 scale-100 opacity-100"
            }`}>
              <PhonePreview
                youtubeThumbnailUrl={youtubeThumbnailUrl}
                fontFamily={fontFamily}
                fontSize={fontSize}
                fontColor={fontColor}
                captionTemplate={captionTemplate}
                availableFonts={availableFonts}
                availableTemplates={availableTemplates}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
