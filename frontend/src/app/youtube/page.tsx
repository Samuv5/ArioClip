"use client";

import { useState, useEffect } from "react";

export default function YouTubeUploadPage() {
  const [videos, setVideos] = useState<string[]>([]);
  const [channels, setChannels] = useState<string[]>([]);
  const [selectedVideo, setSelectedVideo] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);

  // Auth flow
  const [newChannelName, setNewChannelName] = useState("");
  const [authUrl, setAuthUrl] = useState("");
  const [authInstructions, setAuthInstructions] = useState("");
  const [callbackUrl, setCallbackUrl] = useState("");

  // Upload form
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [category, setCategory] = useState("Gente y blogs");
  const [privacy, setPrivacy] = useState("Privado");
  const [madeForKids, setMadeForKids] = useState("No");

  // Status
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
      setStatus("❌ No se pudo conectar con el backend");
    }
  }

  useEffect(() => { fetchData(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function generateAuth() {
    if (!newChannelName.trim()) return;
    setStatus("Generando enlace...");
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
        setStatus("✅ Enlace generado — seguí las instrucciones");
      } else {
        setStatus(`❌ ${data.detail}`);
      }
    } catch { setStatus("❌ Error de conexión"); }
  }

  async function verifyAuth() {
    if (!callbackUrl.trim()) return;
    setStatus("Verificando...");
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
        setStatus("✅ Canal autenticado");
      } else {
        setStatus(`❌ ${data.detail}`);
      }
    } catch { setStatus("❌ Error de conexión"); }
  }

  async function removeChannel(name: string) {
    try {
      const res = await fetch(`${api}/api/youtube/channels/${encodeURIComponent(name)}`, { method: "DELETE" });
      const data = await res.json();
      if (res.ok) {
        setChannels(data.channels);
        setStatus(`✅ Canal "${name}" eliminado`);
      }
    } catch { setStatus("❌ Error"); }
  }

  async function startUpload() {
    if (!selectedVideo) { setStatus("❌ Seleccioná un video"); return; }
    if (!selectedChannels.length) { setStatus("❌ Seleccioná al menos un canal"); return; }
    setUploading(true);
    setStatus("Subiendo... puede tomar varios minutos");
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
    } catch { setStatus("❌ Error de conexión"); }
    setUploading(false);
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold">YouTube Upload</h1>

      {/* Auth Section */}
      <section className="bg-white border rounded-xl p-6 space-y-4">
        <h2 className="text-lg font-semibold">1. Autenticar Canales</h2>
        <div className="flex gap-2">
          <input
            className="flex-1 border rounded-lg px-3 py-2 text-sm"
            placeholder="Nombre identificador (ej: Canal_Gaming)"
            value={newChannelName}
            onChange={(e) => setNewChannelName(e.target.value)}
          />
          <button
            className="bg-black text-white px-4 py-2 rounded-lg text-sm hover:opacity-80"
            onClick={generateAuth}
          >
            Generar enlace
          </button>
        </div>
        {authUrl && (
          <div className="space-y-2">
            <p className="text-xs text-stone-600">{authInstructions}</p>
            <a href={authUrl} target="_blank" rel="noopener noreferrer"
               className="text-blue-600 underline text-sm break-all">{authUrl}</a>
            <div className="flex gap-2">
              <input
                className="flex-1 border rounded-lg px-3 py-2 text-sm"
                placeholder="Pegá la URL COMPLETA de localhost aquí"
                value={callbackUrl}
                onChange={(e) => setCallbackUrl(e.target.value)}
              />
              <button
                className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm hover:opacity-80"
                onClick={verifyAuth}
              >
                Verificar
              </button>
            </div>
          </div>
        )}
        {channels.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-1">Canales autorizados:</p>
            <div className="flex flex-wrap gap-2">
              {channels.map((ch) => (
                <span key={ch} className="bg-stone-100 rounded-full px-3 py-1 text-sm flex items-center gap-2">
                  {ch}
                  <button className="text-red-500 hover:text-red-700" onClick={() => removeChannel(ch)}>×</button>
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Upload Section */}
      <section className="bg-white border rounded-xl p-6 space-y-4">
        <h2 className="text-lg font-semibold">2. Subir Video</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium">Video</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                    value={selectedVideo} onChange={(e) => setSelectedVideo(e.target.value)}>
              <option value="">Seleccionar...</option>
              {videos.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">Categoría</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                    value={category} onChange={(e) => setCategory(e.target.value)}>
              {["Gente y blogs","Entretenimiento","Educación","Ciencia y tecnología","Música",
                "Videojuegos","Deportes","Noticias y política","Comedia","Estilo de vida"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className="text-sm font-medium">Título</label>
            <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                   value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="text-sm font-medium">Descripción</label>
            <textarea className="w-full border rounded-lg px-3 py-2 text-sm mt-1" rows={3}
                      value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="col-span-2">
            <label className="text-sm font-medium">Etiquetas (separadas por coma)</label>
            <input className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                   value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium">Privacidad</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                    value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
              <option>Público</option>
              <option>Oculto</option>
              <option>Privado</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-medium">¿Para niños?</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm mt-1"
                    value={madeForKids} onChange={(e) => setMadeForKids(e.target.value)}>
              <option value="No">No</option>
              <option value="Sí">Sí</option>
            </select>
          </div>
          <div className="col-span-2">
            <label className="text-sm font-medium">Canales destino</label>
            <div className="flex flex-wrap gap-2 mt-1">
              {channels.map((ch) => (
                <label key={ch} className={`cursor-pointer rounded-full px-3 py-1 text-sm border ${
                  selectedChannels.includes(ch) ? "bg-black text-white" : "bg-stone-100"
                }`}>
                  <input type="checkbox" className="hidden"
                         checked={selectedChannels.includes(ch)}
                         onChange={() => setSelectedChannels((prev) =>
                           prev.includes(ch) ? prev.filter((c) => c !== ch) : [...prev, ch]
                         )} />
                  {ch}
                </label>
              ))}
              {channels.length === 0 && <p className="text-sm text-stone-400">Autenticá un canal primero</p>}
            </div>
          </div>
        </div>
        <button
          className="w-full bg-red-600 text-white py-3 rounded-xl text-lg font-semibold hover:opacity-80 disabled:opacity-40"
          disabled={uploading || !selectedVideo || !selectedChannels.length}
          onClick={startUpload}
        >
          {uploading ? "Subiendo..." : "⬆️ SUBIR A YOUTUBE"}
        </button>
      </section>

      {status && (
        <pre className="bg-stone-900 text-green-400 p-4 rounded-xl text-sm whitespace-pre-wrap">
          {status}
        </pre>
      )}
    </div>
  );
}
