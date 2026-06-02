"use client";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip";
import { ThemeToggle } from "@/components/theme-toggle";
import { ArrowLeft, Edit2, Trash2, Check, X, Clock, Clapperboard } from "lucide-react";
import Link from "next/link";
import type { TaskDetails, Clip } from "./types";

interface TaskHeaderProps {
  task: TaskDetails;
  clips: Clip[];
  isEditing: boolean;
  editedTitle: string;
  onEditTitleChange: (val: string) => void;
  onStartEdit: () => void;
  onSaveEdit: () => void;
  onCancelEdit: () => void;
  onDeleteClick: () => void;
  onCancelTask: () => void;
  onResumeTask: () => void;
}

const statusBadge = (status: string, clipsCount: number) => {
  if (status === "completed") {
    return <span>{clipsCount} {clipsCount === 1 ? "clip" : "clips"} generated</span>;
  }
  if (status === "processing") {
    return (
      <div className="relative group">
        <Badge className="bg-blue-100 text-blue-800 cursor-default shimmer">Processing</Badge>
        <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover px-3 py-1.5 text-sm text-popover-foreground shadow-md opacity-0 scale-95 transition-all group-hover:opacity-100 group-hover:scale-100 pointer-events-none">
          🔍&nbsp;&nbsp;We&apos;re currently processing your video. Check back in a couple minutes.
        </div>
      </div>
    );
  }
  if (status === "queued") {
    return <Badge className="bg-yellow-100 text-yellow-800">Queued</Badge>;
  }
  return <Badge variant="outline" className="capitalize">{status}</Badge>;
};

export function TaskHeader({
  task,
  clips,
  isEditing,
  editedTitle,
  onEditTitleChange,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onDeleteClick,
  onCancelTask,
  onResumeTask,
}: TaskHeaderProps) {
  const showShimmer = task.status === "processing" || task.status === "queued";

  return (
    <div className="border-b border-border bg-background">
      <div className="max-w-6xl mx-auto px-4 py-6">
        <div className="flex items-center gap-4 mb-4 justify-between">
          <div className="flex items-center gap-4">
            <Link href="/">
              <Button variant="ghost" size="sm">
                <ArrowLeft className="w-4 h-4" />
                Back
              </Button>
            </Link>
          </div>
          <ThemeToggle />
        </div>

        <div>
          <div className="flex items-center gap-3 mb-2">
            {isEditing ? (
              <div className="flex items-center gap-2 flex-1">
                <Input
                  value={editedTitle}
                  onChange={(e) => onEditTitleChange(e.target.value)}
                  className="text-2xl font-bold h-auto py-1"
                  autoFocus
                />
                <Button size="sm" onClick={onSaveEdit} disabled={!editedTitle.trim()}>
                  <Check className="w-4 h-4" />
                </Button>
                <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                  <X className="w-4 h-4" />
                </Button>
              </div>
            ) : (
              <>
                <h1 className={`text-2xl font-bold text-foreground ${showShimmer ? "shimmer" : ""}`}>
                  {task.source_title}
                </h1>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="ghost" onClick={onStartEdit}>
                    <Edit2 className="w-4 h-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    onClick={onDeleteClick}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </>
            )}
          </div>

          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <Badge variant="outline" className="capitalize">
              {task.source_type}
            </Badge>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="flex items-center gap-1 cursor-default">
                    <Clock className="w-4 h-4" />
                    {new Date(task.created_at).toLocaleDateString(undefined, {
                      year: "numeric", month: "short", day: "numeric",
                    })}
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {new Date(task.created_at).toLocaleString(undefined, {
                    year: "numeric", month: "long", day: "numeric",
                    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: "short",
                  })}
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {statusBadge(task.status, clips.length)}

            {task.status === "completed" && clips.length > 0 && (
              <Link href={`/tasks/${task.id}/edit`}>
                <Button size="sm" variant="outline">
                  <Clapperboard className="w-4 h-4" />
                  Open Editor
                </Button>
              </Link>
            )}

            {(task.status === "queued" || task.status === "processing") && (
              <Button size="sm" variant="outline" onClick={onCancelTask}>
                Cancel
              </Button>
            )}

            {(task.status === "cancelled" || task.status === "error") && (
              <Button size="sm" variant="outline" onClick={onResumeTask}>
                Resume
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
