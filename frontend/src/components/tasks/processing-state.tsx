"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Download } from "lucide-react";
import DynamicVideoPlayer from "@/components/dynamic-video-player";
import type { Clip } from "./types";
import { getClipUrl, formatDuration } from "./task-utils";

interface ProcessingStateProps {
  status: string;
  progress: number;
  progressMessage: string;
  clips: Clip[];
}

export function ProcessingState({ status, progress, progressMessage, clips }: ProcessingStateProps) {
  return (
    <div className="space-y-8">
      <div className="flex flex-col items-center py-8">
        <div className="relative group flex items-center gap-1.5 mb-8 cursor-default">
          <span className="w-2 h-2 bg-foreground rounded-full animate-[pulse_1.4s_ease-in-out_infinite]" />
          <span className="w-2 h-2 bg-foreground rounded-full animate-[pulse_1.4s_ease-in-out_0.2s_infinite]" />
          <span className="w-2 h-2 bg-foreground rounded-full animate-[pulse_1.4s_ease-in-out_0.4s_infinite]" />
          <div className="absolute top-full mt-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md opacity-0 scale-95 transition-all group-hover:opacity-100 group-hover:scale-100 pointer-events-none">
            ☕&nbsp;&nbsp;Grab a coffee, and come back to ready-to-post clips.
          </div>
        </div>

        <p className="text-foreground text-base font-medium tracking-wide mb-6 text-center max-w-lg leading-relaxed">
          {progressMessage || (status === "queued" ? "Waiting in queue" : "Processing")}
        </p>

        {progress > 0 && (
          <div className="w-72">
            <div className="h-1.5 bg-muted w-full rounded-full overflow-hidden">
              <div
                className="h-full bg-foreground rounded-full transition-all duration-500 ease-out"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground text-center mt-2 font-mono tabular-nums">{progress}%</p>
          </div>
        )}
      </div>

      {clips.length > 0 && (
        <div className="grid gap-6">
          <p className="text-sm text-muted-foreground text-center">
            {clips.length} clip{clips.length !== 1 ? "s" : ""} ready
          </p>
          {clips.map((clip) => (
            <Card key={clip.id} className="overflow-hidden">
              <CardContent className="p-0">
                <div className="flex flex-col lg:flex-row">
                  <div className="relative flex-shrink-0 bg-black rounded-lg overflow-hidden m-3">
                    <DynamicVideoPlayer src={getClipUrl(clip.video_url)} poster="/placeholder-video.jpg" />
                  </div>
                  <div className="p-6 flex-1">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="font-semibold text-lg text-foreground mb-1">Clip {clip.clip_order}</h3>
                        <div className="flex items-center gap-2 text-sm text-muted-foreground">
                          <span>{clip.start_time} - {clip.end_time}</span>
                          <span>•</span>
                          <span>{formatDuration(clip.duration)}</span>
                        </div>
                      </div>
                    </div>
                    {clip.text && (
                      <div className="mb-4">
                        <h4 className="font-medium text-foreground mb-2">Transcript</h4>
                        <p className="text-sm text-muted-foreground bg-muted p-3 rounded">{clip.text}</p>
                      </div>
                    )}
                    <Button size="sm" variant="outline" asChild>
                      <a href={getClipUrl(clip.video_url)} download={clip.filename}>
                        <Download className="w-4 h-4" />
                        Download
                      </a>
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
