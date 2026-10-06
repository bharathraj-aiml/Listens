import { useAuth } from "@/store/auth";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function jwtExpiry(token: string): number {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000;
  } catch {
    return 0;
  }
}

let refreshing: Promise<string | null> | null = null;

/** Exchange the refresh token for a new pair. Single-flight: concurrent callers share one request,
 *  which matters because refresh tokens are one-time-use (a second concurrent call would fail). */
function refreshTokens(): Promise<string | null> {
  if (!refreshing) {
    refreshing = (async () => {
      const { refreshToken, setTokens, clear } = useAuth.getState();
      if (!refreshToken) return null;
      const res = await fetch("/api/auth/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) {
        clear();
        return null;
      }
      const data = await res.json();
      setTokens(data.access_token, data.refresh_token);
      return data.access_token as string;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

/** A valid access token, refreshing first if it expires within 30 s. */
export async function getAccessToken(): Promise<string | null> {
  const { accessToken } = useAuth.getState();
  if (accessToken && jwtExpiry(accessToken) - Date.now() > 30_000) return accessToken;
  return (await refreshTokens()) ?? null;
}

async function errorFrom(res: Response): Promise<ApiError> {
  let msg = res.statusText;
  try {
    const body = await res.json();
    msg = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, msg);
}

export async function api<T = unknown>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const send = async (token: string | null) => {
    const headers = new Headers(init.headers);
    if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
    if (auth && token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(path, { ...init, headers });
  };
  let res = await send(auth ? await getAccessToken() : null);
  if (res.status === 401 && auth) {
    const fresh = await refreshTokens();
    if (fresh) res = await send(fresh);
  }
  if (!res.ok) throw await errorFrom(res);
  return res.status === 204 ? (undefined as T) : res.json();
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, body?: unknown, auth = true) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }, auth);

/** Multipart upload with progress (fetch can't report upload progress, XHR can). */
export async function upload<T>(path: string, form: FormData, onProgress: (fraction: number) => void): Promise<T> {
  const token = await getAccessToken();
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onerror = () => reject(new ApiError(0, "Network error"));
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* ignore */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, typeof body?.detail === "string" ? body.detail : xhr.statusText));
    };
    xhr.send(form);
  });
}
