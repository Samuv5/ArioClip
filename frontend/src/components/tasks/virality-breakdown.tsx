"use client";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Zap, MessageSquare, TrendingUp, Star, Share2 } from "lucide-react";
import type { Clip } from "./types";
import { getViralityColor, getHookTypeLabel } from "./task-utils";

interface ViralityBreakdownProps {
  clip: Clip;
}

export function ViralityBreakdown({ clip }: ViralityBreakdownProps) {
  return (
    <div className="mb-4 p-3 bg-muted rounded-lg">
      <div className="flex items-center justify-between mb-3">
        <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
          <Zap className="w-4 h-4" />
          Virality Score
        </h4>
        <span className={`text-lg font-bold ${getViralityColor(clip.virality_score)}`}>
          {clip.virality_score}/100
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-muted-foreground">
              <MessageSquare className="w-3 h-3" />
              Hook
            </span>
            <span className="font-medium">{clip.hook_score}/25</span>
          </div>
          <Progress value={(clip.hook_score / 25) * 100} className="h-1.5" />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-muted-foreground">
              <TrendingUp className="w-3 h-3" />
              Engagement
            </span>
            <span className="font-medium">{clip.engagement_score}/25</span>
          </div>
          <Progress value={(clip.engagement_score / 25) * 100} className="h-1.5" />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-muted-foreground">
              <Star className="w-3 h-3" />
              Value
            </span>
            <span className="font-medium">{clip.value_score}/25</span>
          </div>
          <Progress value={(clip.value_score / 25) * 100} className="h-1.5" />
        </div>

        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1 text-muted-foreground">
              <Share2 className="w-3 h-3" />
              Shareability
            </span>
            <span className="font-medium">{clip.shareability_score}/25</span>
          </div>
          <Progress value={(clip.shareability_score / 25) * 100} className="h-1.5" />
        </div>
      </div>

      {clip.hook_type && clip.hook_type !== "none" && (
        <div className="mt-3 pt-2 border-t">
          <Badge variant="outline" className="text-xs">
            {getHookTypeLabel(clip.hook_type)}
          </Badge>
        </div>
      )}
    </div>
  );
}
