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
  const activeIndex = NAV.findIndex(({ href }) => active(href));

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

      {/* mobile: bottom tab bar. A glass pill slides to the active tab (spring-like overshoot), the active icon
          lifts and pops once when it becomes active. All motion is dropped for prefers-reduced-motion. */}
      <nav aria-label="Main" className="glass-clear fixed inset-x-3 bottom-3 z-30 flex h-14 rounded-full px-2.5 md:hidden">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-1 left-2.5 transition-[transform,opacity] duration-300 ease-[cubic-bezier(0.34,1.4,0.64,1)] motion-reduce:transition-none"
          style={{ width: `calc((100% - 1.25rem) / ${NAV.length})`, transform: `translateX(${Math.max(activeIndex, 0) * 100}%)`, opacity: activeIndex < 0 ? 0 : 1 }}
        >
          <span className="glass-lens -mx-1.5 block h-full rounded-full" />
        </span>
        {NAV.map(({ href, label, Icon }, i) => {
          const isActive = i === activeIndex;
          return (
            <Link
              key={href}
              href={href}
              className={`relative z-10 flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] transition-[color,transform] duration-200 active:scale-90 motion-reduce:transition-none [text-shadow:0_1px_8px_rgba(0,0,0,0.55)] ${isActive ? "text-white" : "text-white/75"}`}
            >
              <span className={`block transition-transform duration-300 motion-reduce:transition-none ${isActive ? "-translate-y-0.5 scale-110 animate-tab-pop" : ""}`}>
                <Icon />
              </span>
              {label}
            </Link>
          );
        })}
      </nav>
    </>
  );
}
