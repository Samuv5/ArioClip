"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import DynamicVideoPlayer from "@/components/dynamic-video-player";
import {
  Download, Star, Zap,
  Scissors, Youtube, Trash2, SplitSquareVertical, RefreshCw, Subtitles,
} from "lucide-react";
import type { Clip, ExportPreset, CaptionPosition } from "./types";
import {
  getClipUrl, formatDuration, getScoreColor, getViralityBgColor,
} from "./task-utils";
import { ViralityBreakdown } from "./virality-breakdown";

interface ClipCardProps {
  clip: Clip;
  exportPreset: ExportPreset;
  editingClipId: string | null;
  startOffset: string;
  endOffset: string;
  splitTime: string;
  captionText: string;
  captionPosition: CaptionPosition;
  highlightWords: string;
  selected: boolean;
  onToggleSelection: () => void;
  onDownload: () => void;
  onExportPresetChange: (preset: ExportPreset) => void;
  onEdit: () => void;
  onYoutube: () => void;
  onDelete: () => void;
  onTrim: () => void;
  onSplit: () => void;
  onRegenerate: () => void;
  onUpdateCaptions: () => void;
  onStartOffsetChange: (val: string) => void;
  onEndOffsetChange: (val: string) => void;
  onSplitTimeChange: (val: string) => void;
  onCaptionTextChange: (val: string) => void;
  onCaptionPositionChange: (val: CaptionPosition) => void;
  onHighlightWordsChange: (val: string) => void;
}

export function ClipCard({
  clip, exportPreset, editingClipId, startOffset, endOffset, splitTime,
  captionText, captionPosition, highlightWords, selected,
  onToggleSelection, onDownload, onExportPresetChange, onEdit, onYoutube,
  onDelete, onTrim, onSplit, onRegenerate, onUpdateCaptions,
  onStartOffsetChange, onEndOffsetChange, onSplitTimeChange,
  onCaptionTextChange, onCaptionPositionChange, onHighlightWordsChange,
}: ClipCardProps) {
  const isEditing = editingClipId === clip.id;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="flex flex-col lg:flex-row">
          {/* Video Player */}
          <div className="relative flex-shrink-0 bg-black rounded-lg overflow-hidden m-3">
            <DynamicVideoPlayer src={getClipUrl(clip.video_url)} poster="/placeholder-video.jpg" />
          </div>

          {/* Clip Details */}
          <div className="p-6 flex-1">
            <div className="flex items-start justify-between mb-4">
              <div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                  <input type="checkbox" checked={selected} onChange={onToggleSelection} />
                  Select for merge
                </label>
                <h3 className="font-semibold text-lg text-foreground mb-1">Clip {clip.clip_order}</h3>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <span>{clip.start_time} - {clip.end_time}</span>
                  <span>•</span>
                  <span>{formatDuration(clip.duration)}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {clip.virality_score > 0 && (
                  <Badge className={`${getViralityBgColor(clip.virality_score)} text-white`}>
                    <Zap className="w-3 h-3 mr-1" />
                    {clip.virality_score}
                  </Badge>
                )}
                <Badge className={getScoreColor(clip.relevance_score)}>
                  <Star className="w-3 h-3 mr-1" />
                  {(clip.relevance_score * 100).toFixed(0)}%
                </Badge>
              </div>
            </div>

            {/* Virality Score Breakdown */}
            {clip.virality_score > 0 && (
              <ViralityBreakdown clip={clip} />
            )}

            {clip.text && (
              <div className="mb-4">
                <h4 className="font-medium text-foreground mb-2">Transcript</h4>
                <p className="text-sm text-muted-foreground bg-muted p-3 rounded">{clip.text}</p>
              </div>
            )}

            <div className="flex items-center gap-2">
              <div className="inline-flex items-stretch h-8 rounded-md border border-input bg-background shadow-xs overflow-hidden">
                <button
                  type="button"
                  onClick={onDownload}
                  className="inline-flex items-center gap-1.5 px-3 text-sm font-medium hover:bg-accent transition-colors focus-visible:outline-none focus-visible:bg-accent"
                >
                  <Download className="w-4 h-4" />
                  Download
                </button>
                <Select value={exportPreset} onValueChange={(v: ExportPreset) => onExportPresetChange(v)}>
                  <SelectTrigger
                    size="sm"
                    aria-label="Download format"
                    className="h-8 min-w-[112px] rounded-none border-0 border-l border-input shadow-none focus-visible:ring-0 focus-visible:border-input bg-transparent"
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent align="end">
                    <SelectItem value="original">Original</SelectItem>
                    <SelectItem value="tiktok">TikTok</SelectItem>
                    <SelectItem value="reels">Reels</SelectItem>
                    <SelectItem value="shorts">Shorts</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button size="sm" variant="outline" onClick={onEdit}>
                <Scissors className="w-4 h-4" />
                Edit
              </Button>

              <Button size="sm" variant="outline" onClick={onYoutube}>
                <Youtube className="w-4 h-4 text-red-500" />
                YouTube
              </Button>

              <Button
                size="sm" variant="ghost" aria-label="Delete clip"
                className="ml-auto text-red-600 hover:text-red-700 hover:bg-red-50"
                onClick={onDelete}
              >
                <Trash2 className="w-4 h-4" />
              </Button>
            </div>

            {isEditing && (
              <div className="mt-4 p-3 border rounded-lg space-y-3 bg-muted">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <Input value={startOffset} onChange={(e) => onStartOffsetChange(e.target.value)} placeholder="Start trim (sec)" />
                  <Input value={endOffset} onChange={(e) => onEndOffsetChange(e.target.value)} placeholder="End trim (sec)" />
                  <Button size="sm" onClick={onTrim}><Scissors className="w-4 h-4" /> Trim</Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <Input value={splitTime} onChange={(e) => onSplitTimeChange(e.target.value)} placeholder="Split at (sec)" />
                  <Button size="sm" variant="outline" onClick={onSplit}><SplitSquareVertical className="w-4 h-4" /> Split</Button>
                  <Button size="sm" variant="outline" onClick={onRegenerate}><RefreshCw className="w-4 h-4" /> Regenerate</Button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                  <Input value={captionText} onChange={(e) => onCaptionTextChange(e.target.value)} placeholder="Caption text" />
                  <Select value={captionPosition} onValueChange={(v: CaptionPosition) => onCaptionPositionChange(v)}>
                    <SelectTrigger><SelectValue placeholder="Caption position" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="top">Top</SelectItem>
                      <SelectItem value="middle">Middle</SelectItem>
                      <SelectItem value="bottom">Bottom</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input value={highlightWords} onChange={(e) => onHighlightWordsChange(e.target.value)} placeholder="Highlights: word1, word2" />
                </div>
                <Button size="sm" variant="outline" onClick={onUpdateCaptions}>
                  <Subtitles className="w-4 h-4" /> Update Captions
                </Button>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
