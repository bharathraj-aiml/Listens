import type { SVGProps } from "react";

const base = (p: SVGProps<SVGSVGElement>) => ({
  width: 20, height: 20, viewBox: "0 0 24 24", fill: "currentColor", "aria-hidden": true, ...p,
});

export const PlayIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M8 5v14l11-7z" /></svg>;
export const PauseIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M7 5h4v14H7zM13 5h4v14h-4z" /></svg>;
export const NextIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6 5l9 7-9 7zM17 5h2v14h-2z" /></svg>;
export const PrevIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M18 5l-9 7 9 7zM5 5h2v14H5z" /></svg>;
export const QueueIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 6h14v2H3zm0 5h14v2H3zm0 5h9v2H3zm13-1v-3l5 3-5 3z" /></svg>;
export const VolumeIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 9v6h4l5 4V5L7 9zm13.5 3a4.5 4.5 0 0 0-2.5-4v8a4.5 4.5 0 0 0 2.5-4z" /></svg>;
export const MuteIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M3 9v6h4l5 4V5L7 9zm13.6 3l2.4-2.4-1.4-1.4-2.4 2.4-2.4-2.4-1.4 1.4 2.4 2.4-2.4 2.4 1.4 1.4 2.4-2.4 2.4 2.4 1.4-1.4z" /></svg>;
export const HomeIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M12 3l9 8h-3v9h-5v-6h-2v6H6v-9H3z" /></svg>;
export const SearchIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M10 2a8 8 0 1 0 5 14.3l5.3 5.3 1.4-1.4-5.3-5.3A8 8 0 0 0 10 2zm0 2a6 6 0 1 1 0 12 6 6 0 0 1 0-12z" /></svg>;
export const UploadIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M11 16V7.8l-3 3L6.6 9.4 12 4l5.4 5.4-1.4 1.4-3-3V16zM5 18h14v2H5z" /></svg>;
export const CloseIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M6.4 5L5 6.4 10.6 12 5 17.6 6.4 19 12 13.4l5.6 5.6 1.4-1.4L13.4 12 19 6.4 17.6 5 12 10.6z" /></svg>;
export const PlusIcon = (p: SVGProps<SVGSVGElement>) => <svg {...base(p)}><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z" /></svg>;
