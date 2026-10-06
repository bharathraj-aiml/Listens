"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import TrackList from "@/components/TrackList";
import { api, get, upload } from "@/lib/api";
import type { Track } from "@/lib/types";

const LICENSES = ["Own work", "Personal library", "CC BY 4.0", "CC BY-SA 4.0", "CC BY-NC 4.0", "CC0 / Public domain"];
type Item = { name: string; progress: number; state: "waiting" | "uploading" | "done" | "duplicate" | "error"; message?: string };

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [license, setLicense] = useState(LICENSES[0]);
  const [rights, setRights] = useState(false);
  const [meta, setMeta] = useState({ title: "", artist: "", album: "", genre: "" });
  const [items, setItems] = useState<Item[]>([]);
  const [busy, setBusy] = useState(false);
  const [mine, setMine] = useState<Track[]>([]);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => get<Track[]>("/api/catalogue/tracks/mine").then(setMine).catch(() => {}), []);
  useEffect(() => { refresh(); }, [refresh]);
  // While anything is still being transcoded, poll so statuses flip to "Ready" on their own.
  const working = mine.some((t) => t.status === "uploaded" || t.status === "processing");
  useEffect(() => {
    if (!working) return;
    const t = setInterval(refresh, 2500);
    return () => clearInterval(t);
  }, [working, refresh]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!files.length || !rights) return;
    setBusy(true);
    const list: Item[] = files.map((f) => ({ name: f.name, progress: 0, state: "waiting" }));
    setItems(list);
    const patch = (i: number, p: Partial<Item>) => setItems((cur) => cur.map((it, k) => (k === i ? { ...it, ...p } : it)));
    for (let i = 0; i < files.length; i++) {
      const form = new FormData();
      form.append("file", files[i]);
      form.append("license", license);
      form.append("rights_confirmed", "true");
      if (files.length === 1) for (const [k, v] of Object.entries(meta)) if (v.trim()) form.append(k, v.trim());
      patch(i, { state: "uploading" });
      try {
        const res = await upload<{ duplicate: boolean }>("/api/catalogue/upload", form, (f) => patch(i, { progress: f }));
        patch(i, { state: res.duplicate ? "duplicate" : "done", progress: 1 });
      } catch (err) {
        patch(i, { state: "error", message: (err as Error).message });
      }
      refresh();
    }
    setBusy(false);
    setFiles([]);
    if (input.current) input.current.value = "";
  }

  async function remove(t: Track) {
    if (!confirm(`Delete “${t.title}”? This removes the audio too.`)) return;
    await api(`/api/catalogue/tracks/${t.id}`, { method: "DELETE" });
    refresh();
  }

  const field = "w-full rounded-lg border border-line bg-raise px-3 py-2 outline-none focus:border-accent";
  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-semibold tracking-tight">Upload music</h1>

      <form onSubmit={submit} className="space-y-4 rounded-xl border border-line bg-panel p-5" data-testid="upload-form">
        <div>
          <label htmlFor="file" className="mb-1 block text-sm text-muted">Audio files (mp3, flac, wav, ogg, opus, m4a)</label>
          <input
            id="file" ref={input} data-testid="file-input" type="file" multiple
            accept=".mp3,.flac,.wav,.ogg,.oga,.opus,.m4a,.aac,audio/*"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="block w-full text-sm text-muted file:mr-3 file:rounded-full file:border-0 file:bg-accent file:px-4 file:py-2 file:font-semibold file:text-ink"
          />
        </div>

        {files.length === 1 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(["title", "artist", "album", "genre"] as const).map((k) => (
              <div key={k}>
                <label htmlFor={k} className="mb-1 block text-sm capitalize text-muted">{k} <span className="text-xs">(optional, read from tags)</span></label>
                <input id={k} className={field} value={meta[k]} onChange={(e) => setMeta({ ...meta, [k]: e.target.value })} />
              </div>
            ))}
          </div>
        )}

        <div>
          <label htmlFor="license" className="mb-1 block text-sm text-muted">License</label>
          <select id="license" data-testid="license" className={field} value={license} onChange={(e) => setLicense(e.target.value)}>
            {LICENSES.map((l) => <option key={l}>{l}</option>)}
          </select>
        </div>

        <label className="flex items-start gap-3 text-sm">
          <input data-testid="rights" type="checkbox" checked={rights} onChange={(e) => setRights(e.target.checked)} className="mt-1" />
          <span>I own this audio or have the right to use it, and I understand uploads are for my private library.</span>
        </label>

        <button
          type="submit" data-testid="upload-submit" disabled={busy || !files.length || !rights}
          className="rounded-full bg-accent px-6 py-2 font-semibold text-ink disabled:opacity-40"
        >
          {busy ? "Uploading…" : files.length > 1 ? `Upload ${files.length} files` : "Upload"}
        </button>
      </form>

      {items.length > 0 && (
        <ul className="space-y-2" data-testid="upload-progress">
          {items.map((it, i) => (
            <li key={i} className="rounded-lg border border-line bg-panel px-4 py-2 text-sm">
              <div className="flex justify-between gap-3">
                <span className="truncate">{it.name}</span>
                <span className={it.state === "error" ? "text-danger" : it.state === "done" ? "text-ok" : "text-muted"}>
                  {it.state === "uploading" ? `${Math.round(it.progress * 100)}%` : it.state === "duplicate" ? "already uploaded" : it.state === "error" ? it.message : it.state}
                </span>
              </div>
              {it.state === "uploading" && <div className="mt-1 h-1 rounded bg-line"><div className="h-1 rounded bg-accent" style={{ width: `${it.progress * 100}%` }} /></div>}
            </li>
          ))}
        </ul>
      )}

      <section>
        <h2 className="mb-2 text-lg font-medium">Your uploads</h2>
        {mine.length === 0 ? <p className="text-sm text-muted">Nothing uploaded yet.</p> : <TrackList tracks={mine} showStatus onDelete={remove} />}
      </section>
    </div>
  );
}
