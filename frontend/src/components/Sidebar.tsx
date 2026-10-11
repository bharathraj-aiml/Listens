"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AlbumIcon, HomeIcon, PlaylistIcon, ProfileIcon, SearchIcon, UploadIcon } from "@/components/icons";
import { Logo } from "@/components/Logo";
import { useAuth } from "@/store/auth";

const NAV = [
  { href: "/", label: "Home", Icon: HomeIcon },
  { href: "/search", label: "Search", Icon: SearchIcon },
  { href: "/playlists", label: "Playlists", Icon: PlaylistIcon },
  { href: "/albums", label: "Albums", Icon: AlbumIcon },
  { href: "/upload", label: "Upload", Icon: UploadIcon },
  { href: "/profile", label: "Profile", Icon: ProfileIcon },
];

/** Just navigation: sign-out lives inside /profile now, not duplicated here too. */
export default function Sidebar() {
  const path = usePathname();
  const { user } = useAuth();
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  return (
    <>
      <nav aria-label="Main" className="glass-surface fixed bottom-3 left-3 top-3 z-20 hidden w-56 flex-col rounded-2xl p-4 md:flex">
        <Link href="/" className="mb-8 mt-2"><Logo /></Link>
        <ul className="space-y-1">
          {NAV.map(({ href, label, Icon }) => (
            <li key={href}>
              <Link href={href} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${active(href) ? "bg-white/15 text-fg shadow-[inset_0_1px_0_rgba(255,255,255,0.25)]" : "text-muted hover:bg-white/10 hover:text-fg"}`}>
                <Icon /> {label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="mt-auto truncate border-t border-line pt-4 text-sm text-muted" data-testid="whoami">{user ? `@${user.username}` : ""}</div>
      </nav>

      {/* mobile: bottom tab bar */}
      <nav aria-label="Main" className="glass-surface fixed inset-x-3 bottom-3 z-30 flex h-14 rounded-2xl md:hidden">
        {NAV.map(({ href, label, Icon }) => (
          <Link key={href} href={href} className={`flex flex-1 flex-col items-center justify-center gap-0.5 text-xs transition-colors active:scale-95 ${active(href) ? "text-accent" : "text-muted"}`}>
            <Icon /> {label}
          </Link>
        ))}
      </nav>
    </>
  );
}
