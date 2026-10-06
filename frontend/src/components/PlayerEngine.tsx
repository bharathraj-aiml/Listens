"use client";

import Hls, { type Level } from "hls.js";
import { useEffect, useRef } from "react";
import { getStreamUrl, invalidateStreamUrl, prefetchTrack } from "@/lib/stream";
import { currentTrack, hydratePlayerPrefs, type Quality, usePlayer } from "@/store/player";

/** Rendition bitrate in kbps. We read it from the variant URL (".../q160/index.m3u8") because the
 *  BANDWIDTH attribute includes container overhead (e.g. 175 000 for a "160k" stream). */
function levelKbps(level: Level): number {
  const url = Array.isArray(level.url) ? level.url[0] : (level.url as unknown as string | undefined);
  const m = url?.match(/\/q(\d+)\//);
  return m ? Number(m[1]) : Math.round(level.bitrate / 1000);
}

function applyQuality(hls: Hls, kbps: number[], quality: Quality, immediate: boolean) {
  let idx = -1; // -1 = hls.js adaptive bitrate
  if (quality !== "auto") {
    idx = kbps.indexOf(quality);
    if (idx < 0) idx = Math.max(0, kbps.filter((k) => k <= quality).length - 1); // best available at or below
  }
  // currentLevel flushes the buffer (instant but may glitch); nextLevel switches at the next segment.
  if (immediate) hls.currentLevel = idx;
  else hls.nextLevel = idx;
}

function onPlayError(e: unknown) {
  if ((e as DOMException)?.name === "AbortError") return; // interrupted by a newer load: expected
  const st = usePlayer.getState();
  st.setPlaying(false);
  st.setError("Playback was blocked. Press play to start.");
}

/**
 * Owns the <audio> element and keeps it in sync with the Zustand player store. Mounted once in the
 * (app) layout, so playback survives client-side navigation between pages.
 */
export default function PlayerEngine() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const hlsRef = useRef<Hls | null>(null);
  const switching = useRef(false); // ignore the <audio> 'pause' events caused by swapping sources
  const pendingSeek = useRef<number | null>(null);
  const lastPositionState = useRef(0);

  const track = usePlayer(currentTrack);
  const nextTrack = usePlayer((s) => s.queue[s.index + 1] ?? null);
  const playing = usePlayer((s) => s.playing);
  const volume = usePlayer((s) => s.volume);
  const muted = usePlayer((s) => s.muted);
  const quality = usePlayer((s) => s.quality);
  const levels = usePlayer((s) => s.levels);
  const seekRequest = usePlayer((s) => s.seekRequest);

  // --- one-time wiring of <audio> events -> store ------------------------------------------
  useEffect(() => {
    hydratePlayerPrefs();
    const audio = audioRef.current!;
    const st = usePlayer.getState;
    const handlers: Record<string, () => void> = {
      timeupdate: () => {
        st().setTime(audio.currentTime);
        const now = Date.now();
        if (now - lastPositionState.current > 1000 && "mediaSession" in navigator && Number.isFinite(audio.duration)) {
          lastPositionState.current = now;
          try {
            navigator.mediaSession.setPositionState({
              duration: audio.duration,
              position: Math.min(audio.currentTime, audio.duration),
              playbackRate: audio.playbackRate,
            });
          } catch {
            /* some browsers reject odd values */
          }
        }
      },
      durationchange: () => Number.isFinite(audio.duration) && st().setDuration(audio.duration),
      loadedmetadata: () => {
        switching.current = false;
        if (pendingSeek.current != null) {
          audio.currentTime = pendingSeek.current;
          pendingSeek.current = null;
        }
      },
      waiting: () => st().setBuffering(true),
      canplay: () => st().setBuffering(false),
      playing: () => {
        switching.current = false;
        st().setBuffering(false);
        st().setError(null);
      },
      // pause caused by something outside the app (headset unplugged, OS media key): reflect it
      pause: () => {
        if (!audio.ended && !switching.current && st().playing) st().setPlaying(false);
      },
      play: () => {
        if (!st().playing) st().setPlaying(true);
      },
      ended: () => st().next(),
      error: () => {
        switching.current = false;
        if (audio.src) st().setError("Couldn't play this track.");
      },
    };
    for (const [ev, fn] of Object.entries(handlers)) audio.addEventListener(ev, fn);
    return () => {
      for (const [ev, fn] of Object.entries(handlers)) audio.removeEventListener(ev, fn);
      hlsRef.current?.destroy();
      audio.pause();
    };
  }, []);

  // --- load the current track ---------------------------------------------------------------
  useEffect(() => {
    const audio = audioRef.current!;
    const st = usePlayer.getState;
    hlsRef.current?.destroy();
    hlsRef.current = null;
    if (!track) {
      audio.removeAttribute("src");
      audio.load();
      st().setLevels([]);
      return;
    }
    let cancelled = false;
    switching.current = true;
    pendingSeek.current = null;
    st().setLevels([]);
    st().setDuration((track.duration_ms ?? 0) / 1000);
    st().setBuffering(true);

    const attach = (url: string, startPosition = -1) => {
      if (Hls.isSupported()) {
        hlsRef.current?.destroy();
        const hls = new Hls({
          // assume a good connection so "auto" starts at the top rendition; ABR then adapts down
          abrEwmaDefaultEstimate: 5_000_000,
          maxBufferLength: 30,
          startPosition,
        });
        hlsRef.current = hls;
        hls.on(Hls.Events.MANIFEST_PARSED, (_e, data) => {
          const kbps = data.levels.map(levelKbps);
          st().setLevels(kbps);
          applyQuality(hls, kbps, st().quality, true);
        });
        let mediaRecoveries = 0;
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal || cancelled) return;
          const code = (data as { response?: { code?: number } }).response?.code;
          if (code === 403) {
            // the signed URL expired mid-track: mint a new one and resume from where we were
            const resumeAt = audio.currentTime;
            invalidateStreamUrl(track.id);
            getStreamUrl(track.id)
              .then((fresh) => !cancelled && attach(fresh, resumeAt))
              .catch(() => st().setError("Stream link expired. Try playing the track again."));
          } else if (data.type === Hls.ErrorTypes.NETWORK_ERROR) hls.startLoad();
          else if (data.type === Hls.ErrorTypes.MEDIA_ERROR && ++mediaRecoveries <= 2) hls.recoverMediaError();
          else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            // retries didn't help: the browser can't decode this stream (e.g. a build without AAC)
            hls.destroy();
            st().setBuffering(false);
            st().setPlaying(false);
            st().setError("Your browser can't decode this audio format.");
          } else st().setError("Couldn't play this track.");
        });
        hls.loadSource(url);
        hls.attachMedia(audio);
      } else if (audio.canPlayType("application/vnd.apple.mpegurl")) {
        audio.src = url; // Safari / iOS: native HLS (no quality control available)
        if (startPosition > 0) pendingSeek.current = startPosition;
      } else {
        st().setError("This browser can't play HLS audio.");
        return false;
      }
      return true;
    };

    (async () => {
      try {
        const url = await getStreamUrl(track.id);
        if (cancelled) return;
        if (attach(url) && st().playing) await audio.play().catch(onPlayError);
      } catch {
        if (!cancelled) {
          switching.current = false;
          st().setBuffering(false);
          st().setError("Couldn't load this track.");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [track?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- play/pause intent ----------------------------------------------------------------------
  useEffect(() => {
    const audio = audioRef.current!;
    if (!audio.src && !hlsRef.current) return; // nothing loaded yet; the load effect starts playback
    if (playing) audio.play().catch(onPlayError);
    else audio.pause();
  }, [playing]);

  // --- volume, seek, quality --------------------------------------------------------------------
  useEffect(() => {
    const audio = audioRef.current!;
    audio.volume = volume;
    audio.muted = muted;
  }, [volume, muted]);

  useEffect(() => {
    if (!seekRequest) return;
    const audio = audioRef.current!;
    if (audio.readyState > 0) audio.currentTime = seekRequest.to;
    else pendingSeek.current = seekRequest.to;
  }, [seekRequest]);

  useEffect(() => {
    if (hlsRef.current && levels.length) applyQuality(hlsRef.current, levels, quality, false);
  }, [quality, levels]);

  // --- prefetch the next track so "next" is instant -----------------------------------------------
  useEffect(() => {
    if (!nextTrack) return;
    const t = setTimeout(() => {
      prefetchTrack(nextTrack.id, usePlayer.getState().quality).catch(() => {});
    }, 3000);
    return () => clearTimeout(t);
  }, [nextTrack?.id, track?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- lock-screen / media-key integration + tab title ----------------------------------------------
  useEffect(() => {
    if (!track) {
      document.title = "Shadow Listens";
      return;
    }
    document.title = `${track.title} · ${track.artist.name}`;
    if (!("mediaSession" in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist.name,
      album: track.album?.title ?? "",
      artwork: track.cover_url ? [{ src: new URL(track.cover_url, location.href).href, sizes: "600x600", type: "image/jpeg" }] : [],
    });
    const st = usePlayer.getState;
    const audio = audioRef.current!;
    const actions: [MediaSessionAction, MediaSessionActionHandler][] = [
      ["play", () => st().setPlaying(true)],
      ["pause", () => st().setPlaying(false)],
      ["previoustrack", () => st().prev()],
      ["nexttrack", () => st().next()],
      ["seekto", (d) => d.seekTime != null && st().requestSeek(d.seekTime)],
      ["seekbackward", () => st().requestSeek(Math.max(0, audio.currentTime - 10))],
      ["seekforward", () => st().requestSeek(audio.currentTime + 10)],
    ];
    for (const [a, h] of actions) {
      try {
        navigator.mediaSession.setActionHandler(a, h);
      } catch {
        /* unsupported action */
      }
    }
  }, [track?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if ("mediaSession" in navigator) navigator.mediaSession.playbackState = playing ? "playing" : "paused";
  }, [playing]);

  return <audio ref={audioRef} preload="auto" data-testid="audio" className="hidden" />;
}
