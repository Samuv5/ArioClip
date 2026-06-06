"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription, SheetFooter } from "@/components/ui/sheet";
import { Settings2, Type } from "lucide-react";
import type { FontOption, CaptionTemplateOption } from "./types";

interface ProjectSettingsSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  fontFamily: string;
  fontSize: string;
  fontColor: string;
  captionTemplate: string;
  includeBroll: boolean;
  cutLongPauses: boolean;
  pauseThresholdMs: string;
  removeFillerWords: boolean;
  filteredWords: string;
  availableFonts: FontOption[];
  availableTemplates: CaptionTemplateOption[];
  isApplying: boolean;
  onFontFamilyChange: (val: string) => void;
  onFontSizeChange: (val: string) => void;
  onFontColorChange: (val: string) => void;
  onCaptionTemplateChange: (val: string) => void;
  onIncludeBrollChange: (val: boolean) => void;
  onCutLongPausesChange: (val: boolean) => void;
  onPauseThresholdMsChange: (val: string) => void;
  onRemoveFillerWordsChange: (val: boolean) => void;
  onFilteredWordsChange: (val: string) => void;
  onApply: () => void;
}

export function ProjectSettingsSheet({
  open, onOpenChange,
  fontFamily, fontSize, fontColor, captionTemplate,
  includeBroll, cutLongPauses, pauseThresholdMs, removeFillerWords, filteredWords,
  availableFonts, availableTemplates, isApplying,
  onFontFamilyChange, onFontSizeChange, onFontColorChange, onCaptionTemplateChange,
  onIncludeBrollChange, onCutLongPausesChange, onPauseThresholdMsChange,
  onRemoveFillerWordsChange, onFilteredWordsChange, onApply,
}: ProjectSettingsSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Settings2 className="w-4 h-4" />
            Project Settings
          </SheetTitle>
          <SheetDescription>
            Configure font, caption, and B-roll settings for this task&apos;s clips.
          </SheetDescription>
        </SheetHeader>

        <div className="space-y-5 px-4">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Font</label>
            <Select value={fontFamily} onValueChange={onFontFamilyChange}>
              <SelectTrigger>
                <SelectValue placeholder="Font family" />
              </SelectTrigger>
              <SelectContent>
                {availableFonts.map((font) => (
                  <SelectItem key={font.name} value={font.name}>
                    <span className="flex items-center gap-2">
                      <Type className="w-3 h-3" />
                      {font.display_name}
                    </span>
                  </SelectItem>
                ))}
                {availableFonts.length === 0 && (
                  <SelectItem value="TikTokSans-Regular">TikTok Sans Regular</SelectItem>
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Size</label>
            <Input type="number" min={12} max={72}
              value={fontSize} onChange={(e) => onFontSizeChange(e.target.value)}
              placeholder="Font size"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Color</label>
            <div className="flex items-center gap-2">
              <input type="color" value={fontColor}
                onChange={(e) => onFontColorChange(e.target.value)}
                className="h-9 w-9 rounded border border-border cursor-pointer"
              />
              <Input value={fontColor} onChange={(e) => onFontColorChange(e.target.value)} placeholder="#FFFFFF" />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Caption Template</label>
            <Select value={captionTemplate} onValueChange={onCaptionTemplateChange}>
              <SelectTrigger>
                <SelectValue>
                  {availableTemplates.find((t) => t.id === captionTemplate)?.name || "Select style"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {availableTemplates.map((template) => (
                  <SelectItem key={template.id} value={template.id}>
                    <div>
                      <div className="font-medium">{template.name}</div>
                      <div className="text-xs text-muted-foreground">{template.description}</div>
                    </div>
                  </SelectItem>
                ))}
                {availableTemplates.length === 0 && <SelectItem value="default">Default</SelectItem>}
              </SelectContent>
            </Select>
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input type="checkbox" checked={includeBroll}
              onChange={(e) => onIncludeBrollChange(e.target.checked)} className="rounded"
            />
            Include B-roll
          </label>

          <div className="rounded-lg border bg-muted p-3 space-y-3">
            <div>
              <div className="text-sm font-medium text-foreground">Clip cleanup</div>
              <div className="text-xs text-muted-foreground">Apply silence and filler-word cuts to regenerated clips.</div>
            </div>

            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={cutLongPauses}
                onChange={(e) => onCutLongPausesChange(e.target.checked)} className="rounded"
              />
              Cut long pauses
            </label>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Pause threshold (ms)</label>
              <Input type="number" min={250} max={3000} step={50}
                value={pauseThresholdMs} onChange={(e) => onPauseThresholdMsChange(e.target.value)}
                disabled={!cutLongPauses}
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input type="checkbox" checked={removeFillerWords}
                onChange={(e) => onRemoveFillerWordsChange(e.target.checked)} className="rounded"
              />
              Remove filler words
            </label>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Extra filtered words or phrases</label>
              <Input value={filteredWords} onChange={(e) => onFilteredWordsChange(e.target.value)}
                placeholder="basically, literally, to be honest"
              />
            </div>
          </div>
        </div>

        <SheetFooter>
          <Button className="w-full" onClick={onApply} disabled={isApplying}>
            {isApplying ? "Applying..." : "Apply to All Clips"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
