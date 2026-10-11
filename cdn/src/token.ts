/** Verifies the signed stream/cover tokens minted by libs/common/listens_common/signing.py:
 *
 *     token = base64url(json payload) "." base64url(HMAC-SHA256(secret, base64url(json payload)))
 *     payload = {"k": "hls" | "cover", "t": <track uuid>, "e": <expiry, unix seconds>, "u": <user uuid, optional>}
 *
 * Same rules as the Python side: bad MAC, wrong kind, expired or malformed all fail. */

export type TokenKind = "hls" | "cover";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function unb64url(text: string): Uint8Array {
  const b64 = text.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

/** The track id when the token is valid for `kind`, otherwise null. */
export async function verifyToken(secret: string, token: string, kind: TokenKind, nowMs = Date.now()): Promise<string | null> {
  try {
    const dot = token.indexOf(".");
    if (dot < 1) return null;
    const body = token.slice(0, dot);
    const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
    // subtle.verify compares in constant time, so it does not leak how many MAC bytes matched
    const ok = await crypto.subtle.verify("HMAC", key, unb64url(token.slice(dot + 1)), new TextEncoder().encode(body));
    if (!ok) return null;
    const payload = JSON.parse(new TextDecoder().decode(unb64url(body)));
    if (payload.k !== kind || typeof payload.e !== "number" || payload.e < nowMs / 1000) return null;
    return typeof payload.t === "string" && UUID.test(payload.t) ? payload.t.toLowerCase() : null;
  } catch {
    return null;
  }
}
