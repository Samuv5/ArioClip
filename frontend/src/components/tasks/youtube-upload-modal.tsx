"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { X, Youtube, Upload } from "lucide-react";
import type { Clip, TaskDetails } from "./types";

interface YouTubeUploadModalProps {
  clip: Clip | null;
  task: TaskDetails | null;
  apiUrl: string;
  onClose: () => void;
}

export function YouTubeUploadModal({ clip, task, apiUrl, onClose }: YouTubeUploadModalProps) {
  const [channels, setChannels] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [status, setStatus] = useState("");
  const [suggesting, setSuggesting] = useState(true);

  useEffect(() => {
    if (!clip) return;
    setSelectedChannels([]);
    setUploading(false);
    setStatus("");
    setTitle("");
    setDescription("");
    setSuggesting(true);

    fetch(`${apiUrl}/api/youtube/channels`)
      .then((r) => r.ok && r.json())
      .then((data) => data && setChannels(data))
      .catch(() => {});

    fetch(`${apiUrl}/api/youtube/generate-metadata`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clip_text: clip.text,
        source_title: task?.source_title || "",
        original_url: task?.source_url || "",
      }),
    })
      .then((r) => r.ok && r.json())
      .then((data) => {
        if (data) {
          setTitle(data.title || "");
          setDescription(data.description || "");
        }
      })
      .catch(() => {})
      .finally(() => setSuggesting(false));
  }, [clip, task, apiUrl]);

  if (!clip) return null;

  const handleUpload = async () => {
    if (!selectedChannels.length) return;
    setUploading(true);
    setStatus("Uploading...");
    try {
      const res = await fetch(`${apiUrl}/api/youtube/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video: clip.filename,
          title,
          description,
          tags: task?.source_title || "",
          channels: selectedChannels,
        }),
      });
      const data = await res.json();
      if (res.ok) setStatus(data.results?.join("\n") || "Uploaded");
      else setStatus(`Error: ${data.detail || "Unknown error"}`);
    } catch {
      setStatus("Error uploading");
    }
    setUploading(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !uploading && onClose()}>
      <div className="bg-background rounded-xl max-w-lg w-full max-h-[90vh] overflow-y-auto p-6 space-y-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Youtube className="w-5 h-5 text-red-500" />
            Upload to YouTube
          </h2>
          <button className="text-muted-foreground hover:text-muted-foreground" onClick={onClose}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-muted-foreground">
          Clip #{clip.clip_order} — {clip.start_time} to {clip.end_time}
        </p>

        <div>
          <label className="text-sm font-medium block mb-1">Title</label>
          {suggesting ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="w-4 h-4 border-2 border-border border-t-blue-500 rounded-full animate-spin" />
              Generating AI suggestion...
            </div>
          ) : null}
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Video title" />
        </div>

        <div>
          <label className="text-sm font-medium block mb-1">Description</label>
          <textarea
            className="w-full min-h-[100px] border rounded-lg px-3 py-2 text-sm"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Video description"
          />
        </div>

        {task?.source_url && (
          <div>
            <label className="text-sm font-medium block mb-1">Original video link</label>
            <Input value={task.source_url} readOnly className="text-xs text-blue-600" />
          </div>
        )}

        <div>
          <label className="text-sm font-medium block mb-1">Target channels</label>
          {channels.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No channels authenticated.{" "}
              <a href="/youtube" className="text-blue-600 underline" target="_blank">Manage channels</a>
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {channels.map((ch) => (
                <label key={ch} className={`cursor-pointer rounded-full px-3 py-1 text-sm border ${
                  selectedChannels.includes(ch) ? "bg-red-600 text-white border-red-600" : "bg-muted"
                }`}>
                  <input type="checkbox" className="hidden"
                    checked={selectedChannels.includes(ch)}
                    onChange={() => setSelectedChannels((prev) =>
                      prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
                    )} />
                  {ch}
                </label>
              ))}
            </div>
          )}
        </div>

        <Button
          className="w-full bg-red-600 hover:bg-red-700 text-white"
          disabled={uploading || !title || !selectedChannels.length}
          onClick={handleUpload}
        >
          {uploading ? (
            <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" /> Uploading...</>
          ) : (
            <><Upload className="w-4 h-4 mr-2" /> Upload to YouTube</>
          )}
        </Button>

        {status && (
          <pre className="bg-stone-900 text-green-400 p-3 rounded-lg text-sm whitespace-pre-wrap">
            {status}
          </pre>
        )}
      </div>
    </div>
  );
}
