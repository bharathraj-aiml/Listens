"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { HomeIcon, SearchIcon, UploadIcon } from "@/components/icons";
import { Logo } from "@/components/Logo";
import { post } from "@/lib/api";
import { useAuth } from "@/store/auth";
import { usePlayer } from "@/store/player";

const NAV = [
  { href: "/", label: "Home", Icon: HomeIcon },
  { href: "/search", label: "Search", Icon: SearchIcon },
  { href: "/upload", label: "Upload", Icon: UploadIcon },
];

export default function Sidebar() {
  const path = usePathname();
  const router = useRouter();
  const { user, refreshToken, clear } = useAuth();

  async function logout() {
    try {
      if (refreshToken) await post("/api/auth/logout", { refresh_token: refreshToken }, false);
    } catch {
      /* logging out locally is enough if the server is unreachable */
    }
    usePlayer.getState().playQueue([]);
    clear();
    router.replace("/login");
  }

  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <>
      <nav aria-label="Main" className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-line bg-panel p-4 md:flex">
        <Link href="/" className="mb-8 mt-2"><Logo /></Link>
        <ul className="space-y-1">
          {NAV.map(({ href, label, Icon }) => (
            <li key={href}>
              <Link href={href} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${active(href) ? "bg-raise text-fg" : "text-muted hover:bg-raise/60 hover:text-fg"}`}>
                <Icon /> {label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="mt-auto border-t border-line pt-4 text-sm">
          <div className="truncate text-muted" data-testid="whoami">{user ? `@${user.username}` : ""}</div>
          <button onClick={logout} data-testid="logout" className="mt-2 text-muted hover:text-fg">Sign out</button>
        </div>
      </nav>

      {/* mobile: bottom tab bar */}
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-30 flex h-14 border-t border-line bg-panel md:hidden">
        {NAV.map(({ href, label, Icon }) => (
          <Link key={href} href={href} className={`flex flex-1 flex-col items-center justify-center gap-0.5 text-xs ${active(href) ? "text-accent" : "text-muted"}`}>
            <Icon /> {label}
          </Link>
        ))}
        <button onClick={logout} className="flex flex-1 flex-col items-center justify-center text-xs text-muted">Sign out</button>
      </nav>
    </>
  );
}
