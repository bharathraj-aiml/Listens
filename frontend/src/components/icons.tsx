import {
  House, MagnifyingGlass, Pause, Play, Plus, Queue, SkipBack, SkipForward,
  SpeakerHigh, SpeakerX, UploadSimple, X, type Icon, type IconProps,
} from "@phosphor-icons/react";

/** Phosphor icon set, "bold" weight, standardised to 20px unless a caller overrides size/width/height.
 *  aria-hidden by default: every call site wraps these in a button that already carries aria-label. */
const wrap = (Base: Icon) => {
  const Wrapped = (p: IconProps) => <Base weight="bold" size={20} aria-hidden {...p} />;
  Wrapped.displayName = Base.displayName;
  return Wrapped;
};

export const PlayIcon = wrap(Play);
export const PauseIcon = wrap(Pause);
export const NextIcon = wrap(SkipForward);
export const PrevIcon = wrap(SkipBack);
export const QueueIcon = wrap(Queue);
export const VolumeIcon = wrap(SpeakerHigh);
export const MuteIcon = wrap(SpeakerX);
export const HomeIcon = wrap(House);
export const SearchIcon = wrap(MagnifyingGlass);
export const UploadIcon = wrap(UploadSimple);
export const CloseIcon = wrap(X);
export const PlusIcon = wrap(Plus);
