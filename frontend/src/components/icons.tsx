import {
  Bell, CaretDown, CaretRight, CaretUp, ChartBar, ChartLineUp, ClockCounterClockwise, CloudArrowDown, DeviceMobile, Disc,
  Gear, Heart, House, IdentificationCard, Info, Lock, MagnifyingGlass, Pause, PencilSimple, Play, Playlist, Plus,
  Queue, Repeat, RepeatOnce, Shuffle, SkipBack, SkipForward, SlidersHorizontal, Sparkle, SpeakerHigh, SpeakerX,
  TextAlignLeft, Trash, UploadSimple, UserCircle, Waveform, X,
  type Icon, type IconProps,
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
export const HeartIcon = wrap(Heart);
export const LyricsIcon = wrap(TextAlignLeft);
export const PlaylistIcon = wrap(Playlist);
export const EditIcon = wrap(PencilSimple);
export const TrashIcon = wrap(Trash);
export const CaretUpIcon = wrap(CaretUp);
export const CaretDownIcon = wrap(CaretDown);
export const CaretRightIcon = wrap(CaretRight);
export const AnalyticsIcon = wrap(ChartBar);
export const SimilarIcon = wrap(Sparkle);
export const ProfileIcon = wrap(UserCircle);
export const ShuffleIcon = wrap(Shuffle);
export const RepeatIcon = wrap(Repeat);
export const RepeatOnceIcon = wrap(RepeatOnce);
export const AccountIcon = wrap(IdentificationCard);
export const ContentDisplayIcon = wrap(SlidersHorizontal);
export const PrivacyIcon = wrap(Lock);
export const PlaybackIcon = wrap(Waveform);
export const NotificationsIcon = wrap(Bell);
export const DevicesIcon = wrap(DeviceMobile);
export const DataSavingIcon = wrap(CloudArrowDown);
export const AboutIcon = wrap(Info);
export const SettingsIcon = wrap(Gear);
export const RecentsIcon = wrap(ClockCounterClockwise);
export const StatsIcon = wrap(ChartLineUp);
export const AlbumIcon = wrap(Disc);
