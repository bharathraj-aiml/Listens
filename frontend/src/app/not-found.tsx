import Link from "next/link";
import { LogoMark } from "@/components/Logo";

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <LogoMark size={40} />
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="max-w-sm text-sm text-muted">There's nothing at this address. It might have been moved or deleted.</p>
      <Link href="/" className="mt-2 rounded-full bg-accent px-5 py-2 text-sm font-semibold text-ink hover:brightness-110">
        Back to Home
      </Link>
    </div>
  );
}
