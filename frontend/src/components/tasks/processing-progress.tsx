"use client";

import { Progress } from "@/components/ui/progress";
import { CheckCircle, Loader2, Youtube } from "lucide-react";

interface ProcessingProgressProps {
  progress: number;
  currentStep: string;
  statusMessage: string;
  sourceTitle: string | null;
}

const getStepIcon = (step: string) => {
  const iconMap: Record<string, React.ReactElement> = {
    validation: <Loader2 className="w-4 h-4 animate-spin text-blue-500" />,
    user_check: <Loader2 className="w-4 h-4 animate-spin text-blue-500" />,
    source_analysis: <Loader2 className="w-4 h-4 animate-spin text-blue-500" />,
    youtube_info: <Youtube className="w-4 h-4 text-red-500" />,
    database_save: <Loader2 className="w-4 h-4 animate-spin text-blue-500" />,
    download: <Loader2 className="w-4 h-4 animate-spin text-green-500" />,
    transcript: <Loader2 className="w-4 h-4 animate-spin text-purple-500" />,
    ai_analysis: <Loader2 className="w-4 h-4 animate-spin text-orange-500" />,
    clip_generation: <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />,
    save_clips: <Loader2 className="w-4 h-4 animate-spin text-pink-500" />,
    complete: <CheckCircle className="w-4 h-4 text-green-500" />,
  };
  return iconMap[step] || <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />;
};

export function ProcessingProgress({ progress, currentStep, statusMessage, sourceTitle }: ProcessingProgressProps) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">Processing</span>
          <span className="text-foreground font-medium">{progress}%</span>
        </div>
        <Progress value={progress} className="h-2" />
      </div>

      {currentStep && statusMessage && (
        <div className="bg-muted rounded-xl p-4 space-y-3 border border-border">
          <div className="flex items-center gap-3">
            {getStepIcon(currentStep)}
            <div className="flex-1">
              <p className="text-sm font-medium text-foreground">{statusMessage}</p>
              {sourceTitle && (
                <p className="text-xs text-muted-foreground mt-1">Processing: {sourceTitle}</p>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              { step: "Validation", key: "validation", threshold: 15 },
              { step: "Download", key: "download", threshold: 30 },
              { step: "Transcript", key: "transcript", threshold: 45 },
              { step: "AI Analysis", key: "ai_analysis", threshold: 60 },
              { step: "Create Clips", key: "clip_generation", threshold: 75 },
              { step: "Complete", key: "complete", threshold: 100 },
            ].map((item) => (
              <div
                key={item.key}
                className={`flex items-center gap-2 p-2 rounded-lg ${
                  currentStep === item.key || (item.key === "clip_generation" && currentStep === "save_clips")
                    ? item.key === "validation" || item.key === "user_check"
                      ? "bg-blue-100"
                      : item.key === "download"
                        ? "bg-green-100"
                        : item.key === "transcript"
                          ? "bg-purple-100"
                          : item.key === "ai_analysis"
                            ? "bg-orange-100"
                            : item.key === "clip_generation" || currentStep === "save_clips"
                              ? "bg-indigo-100"
                              : "bg-green-100"
                    : progress >= item.threshold
                      ? "bg-green-100"
                      : "bg-muted"
                }`}
              >
                <CheckCircle className={`w-3 h-3 ${progress >= item.threshold ? "text-green-500" : "text-muted-foreground"}`} />
                <span className={progress >= item.threshold ? "text-green-700" : "text-muted-foreground"}>{item.step}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
