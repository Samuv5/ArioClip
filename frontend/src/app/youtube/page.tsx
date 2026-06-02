"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowLeft, Youtube, Upload, X, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function YouTubeUploadPage() {
  const [videos, setVideos] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);

  const [newChannelName, setNewChannelName] = useState("");
  const [authUrl, setAuthUrl] = useState("");
  const [authInstructions, setAuthInstructions] = useState("");
  const [callbackUrl, setCallbackUrl] = useState("");

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [category, setCategory] = useState("Gente y blogs");
  const [privacy, setPrivacy] = useState("Privado");
  const [madeForKids, setMadeForKids] = useState("No");

  const [status, setStatus] = useState("");
  const [uploading, setUploading] = useState(false);

  const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  async function fetchData() {
    try {
      const [vRes, cRes] = await Promise.all([
        fetch(`${api}/api/youtube/videos`),
        fetch(`${api}/api/youtube/channels`),
      ]);
      if (vRes.ok) setVideos(await vRes.json());
      if (cRes.ok) setChannels(await cRes.json());
    } catch {
      setStatus("❌ Could not connect to backend");
    }
  }

  useEffect(() => { fetchData(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function generateAuth() {
    if (!newChannelName.trim()) return;
    setStatus("Generating auth link...");
    try {
      const res = await fetch(`${api}/api/youtube/auth-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_name: newChannelName.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setAuthUrl(data.url);
        setAuthInstructions(data.message);
        setStatus("✅ Auth link ready — follow the instructions");
      } else {
        setStatus(`❌ ${data.detail}`);
      }
    } catch {
      setStatus("❌ Connection error");
    }
  }

  async function verifyAuth() {
    if (!callbackUrl.trim()) return;
    setStatus("Verifying...");
    try {
      const res = await fetch(`${api}/api/youtube/auth-callback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ channel_name: newChannelName.trim(), callback_url: callbackUrl.trim() }),
      });
      const data = await res.json();
      if (res.ok) {
        setChannels(data.channels);
        setNewChannelName("");
        setCallbackUrl("");
        setAuthUrl("");
        setAuthInstructions("");
        setStatus("✅ Channel authenticated");
      } else {
        setStatus(`❌ ${data.detail}`);
      }
    } catch {
      setStatus("❌ Connection error");
    }
  }

  async function removeChannel(name: string) {
    try {
      const res = await fetch(`${api}/api/youtube/channels/${encodeURIComponent(name)}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        setChannels(data.channels);
        setStatus(`✅ Channel "${name}" removed`);
      }
    } catch {
      setStatus("❌ Error");
    }
  }

  async function startUpload() {
    if (!selectedVideo) { setStatus("❌ Select a video"); return; }
    if (!selectedChannels.length) { setStatus("❌ Select at least one channel"); return; }
    setUploading(true);
    setStatus("Uploading... this may take several minutes");
    try {
      const res = await fetch(`${api}/api/youtube/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video: selectedVideo,
          title,
          description,
          tags,
          category,
          privacy,
          made_for_kids: madeForKids,
          channels: selectedChannels,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setStatus(data.results.join("\n"));
      } else {
        setStatus(`❌ ${data.detail}`);
      }
    } catch {
      setStatus("❌ Connection error");
    }
    setUploading(false);
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border bg-background">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Link href="/">
              <Button variant="ghost" size="icon" className="shrink-0">
                <ArrowLeft className="w-5 h-5" />
              </Button>
            </Link>
            <div>
              <h1 className="text-2xl font-semibold flex items-center gap-2">
                <Youtube className="w-6 h-6 text-red-500" />
                YouTube Upload
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                Authenticate channels and upload your clips
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="space-y-6">
          {/* ── Auth Section ── */}
          <Card>
            <CardContent className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">1. Authenticate Channels</h2>
                {channels.length > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {channels.length} channel{channels.length > 1 ? "s" : ""}
                  </Badge>
                )}
              </div>

              <div className="flex gap-2">
                <Input
                  placeholder="Channel name (e.g. MyGamingChannel)"
                  value={newChannelName}
                  onChange={(e) => setNewChannelName(e.target.value)}
                />
                <Button onClick={generateAuth} disabled={!newChannelName.trim()}>
                  Generate link
                </Button>
              </div>

              {authUrl && (
                <div className="bg-muted rounded-lg p-4 space-y-3 border">
                  <p className="text-sm text-muted-foreground">{authInstructions}</p>
                  <a
                    href={authUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-sm text-blue-600 underline break-all"
                  >
                    <ExternalLink className="w-3 h-3 shrink-0" />
                    {authUrl}
                  </a>
                  <div className="flex gap-2">
                    <Input
                      placeholder="Paste the FULL redirect URL here"
                      value={callbackUrl}
                      onChange={(e) => setCallbackUrl(e.target.value)}
                    />
                    <Button variant="secondary" onClick={verifyAuth} disabled={!callbackUrl.trim()}>
                      Verify
                    </Button>
                  </div>
                </div>
              )}

              {channels.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {channels.map((ch) => (
                    <Badge key={ch} variant="secondary" className="pl-3 pr-2 py-1.5 gap-2 text-sm">
                      {ch}
                      <button className="text-red-500 hover:text-red-700" onClick={() => removeChannel(ch)}>
                        <X className="w-3 h-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* ── Upload Section ── */}
          <Card>
            <CardContent className="p-6 space-y-4">
              <h2 className="text-lg font-semibold">2. Upload Video</h2>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Video file</label>
                  <Select value={selectedVideo} onValueChange={setSelectedVideo}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a video..." />
                    </SelectTrigger>
                    <SelectContent>
                      {videos.map((v) => (
                        <SelectItem key={v} value={v}>{v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Category</label>
                  <Select value={category} onValueChange={setCategory}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["Gente y blogs","Entretenimiento","Educación","Ciencia y tecnología","Música",
                        "Videojuegos","Deportes","Noticias y política","Comedia","Estilo de vida"].map((c) => (
                        <SelectItem key={c} value={c}>{c}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-sm font-medium">Title</label>
                  <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Video title" />
                </div>

                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-sm font-medium">Description</label>
                  <textarea
                    className="w-full min-h-[100px] rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:border-black"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Video description"
                  />
                </div>

                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-sm font-medium">Tags (comma separated)</label>
                  <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="tag1, tag2, tag3" />
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Privacy</label>
                  <Select value={privacy} onValueChange={setPrivacy}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Público">Public</SelectItem>
                      <SelectItem value="Oculto">Unlisted</SelectItem>
                      <SelectItem value="Privado">Private</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-sm font-medium">Made for kids?</label>
                  <Select value={madeForKids} onValueChange={setMadeForKids}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="No">No</SelectItem>
                      <SelectItem value="Sí">Yes</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="sm:col-span-2 space-y-1.5">
                  <label className="text-sm font-medium">Target channels</label>
                  {channels.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Authenticate a channel first in the section above.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {channels.map((ch) => (
                        <label
                          key={ch}
                          className={`cursor-pointer rounded-full px-3 py-1.5 text-sm border transition-colors ${
                            selectedChannels.includes(ch)
                              ? "bg-red-600 text-white border-red-600"
                              : "bg-muted hover:bg-muted"
                          }`}
                        >
                          <input
                            type="checkbox"
                            className="hidden"
                            checked={selectedChannels.includes(ch)}
                            onChange={() =>
                              setSelectedChannels((prev) =>
                                prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
                              )
                            }
                          />
                          {ch}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <Button
                className="w-full"
                size="lg"
                disabled={uploading || !selectedVideo || !selectedChannels.length}
                onClick={startUpload}
              >
                {uploading ? (
                  <><div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2" /> Uploading...</>
                ) : (
                  <><Upload className="w-4 h-4 mr-2" /> Upload to YouTube</>
                )}
              </Button>
            </CardContent>
          </Card>

          {status && (
            <pre className="bg-stone-900 text-green-400 p-4 rounded-xl text-sm whitespace-pre-wrap leading-relaxed">
              {status}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
