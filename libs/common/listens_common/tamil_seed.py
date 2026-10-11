"""A small built-in map of Tamil film-music singers and composers, used where the open data is thin.

ListenBrainz knows the 2010s well but is sparse for 80s/90s artists, and Tamil songs are usually
tagged with romanised titles, so language and release year are often unknown. For the artists
listed here the recommender gets three things for free:

  era       the years the artist was at their commercial peak (approximate, deliberately broad),
            used as the track's year when its album has no release date
  circle    "classic" (peak starting before ~2005) or "modern": artists in the same circle get a
            baseline affinity, so Mano, Janaki and SPB read as neighbours even with no
            listening data linking them
  language  "ta" for artists who work almost entirely in Tamil. Left out for singers who split
            their time across languages (SPB, Hariharan, Udit Narayan, Shreya Ghoshal...),
            where it would be a guess.

Names are matched ignoring case, dots and spaces, and a joint credit ("Mano, S. Janaki") matches on
whichever part is listed. Extend SEED freely; nothing else needs to change.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CLASSIC, MODERN = "classic", "modern"


@dataclass(frozen=True)
class Entry:
    name: str
    peak: tuple[int, int]
    circle: str
    tamil_core: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def year(self) -> int:
        return (self.peak[0] + self.peak[1]) // 2


SEED = [
    # composers
    Entry("Ilaiyaraaja", (1976, 1999), CLASSIC, True, ("Ilayaraja", "Ilaiyaraja", "Ilayaraaja", "Isaignani Ilaiyaraaja", "Maestro Ilaiyaraaja")),
    Entry("A. R. Rahman", (1992, 2010), CLASSIC, False, ("AR Rahman", "A.R. Rahman", "A R Rahman", "Rahman")),
    Entry("Deva", (1990, 2005), CLASSIC, True, ("Thenisai Thendral Deva",)),
    Entry("Vidyasagar", (1995, 2010), CLASSIC, False),
    Entry("S. A. Rajkumar", (1992, 2002), CLASSIC, True, ("SA Rajkumar",)),
    Entry("Sirpy", (1990, 2000), CLASSIC, True),
    Entry("Karthik Raja", (1995, 2005), CLASSIC, True),
    Entry("Gangai Amaran", (1980, 1995), CLASSIC, True),
    # 80s / 90s playback singers
    Entry("S. P. Balasubrahmanyam", (1980, 2000), CLASSIC, False, ("SPB", "S.P.B", "S. P. Balasubramaniam", "SP Balasubrahmanyam", "Balu")),
    Entry("S. Janaki", (1975, 2000), CLASSIC, False, ("Janaki", "S Janaki")),
    Entry("K. S. Chithra", (1985, 2010), CLASSIC, False, ("Chithra", "KS Chithra")),
    Entry("Mano", (1990, 2005), CLASSIC, True),
    Entry("Swarnalatha", (1990, 2000), CLASSIC, True),
    Entry("Malaysia Vasudevan", (1975, 1998), CLASSIC, True),
    Entry("K. J. Yesudas", (1970, 1995), CLASSIC, False, ("Yesudas", "KJ Yesudas")),
    Entry("Hariharan", (1992, 2010), CLASSIC),
    Entry("Unni Menon", (1990, 2000), CLASSIC),
    Entry("Srinivas", (1995, 2005), CLASSIC),
    Entry("Sujatha Mohan", (1990, 2005), CLASSIC, False, ("Sujatha",)),
    Entry("Minmini", (1992, 1998), CLASSIC, True),
    Entry("Sadhana Sargam", (1992, 2005), CLASSIC),
    Entry("Anuradha Sriram", (1993, 2005), CLASSIC, True),
    Entry("Mahalakshmi Iyer", (1998, 2008), CLASSIC),
    Entry("Shankar Mahadevan", (1998, 2012), CLASSIC),
    Entry("Udit Narayan", (1992, 2008), CLASSIC),
    Entry("Vani Jairam", (1975, 1990), CLASSIC),
    Entry("S. N. Surendar", (1985, 2000), CLASSIC, True, ("SN Surendar",)),
    Entry("Arunmozhi", (1985, 2000), CLASSIC, True),
    # modern
    Entry("Anirudh Ravichander", (2012, 2025), MODERN, True, ("Anirudh",)),
    Entry("Yuvan Shankar Raja", (2001, 2015), MODERN, True, ("Yuvan",)),
    Entry("Harris Jayaraj", (2001, 2012), MODERN, True),
    Entry("G. V. Prakash Kumar", (2006, 2022), MODERN, True, ("GV Prakash", "G.V. Prakash", "GV Prakash Kumar")),
    Entry("D. Imman", (2010, 2025), MODERN, True, ("D Imman", "Imman")),
    Entry("Santhosh Narayanan", (2012, 2025), MODERN, True),
    Entry("Hiphop Tamizha", (2012, 2025), MODERN, True, ("Hip Hop Tamizha",)),
    Entry("Sid Sriram", (2016, 2025), MODERN),
    Entry("Karthik", (2002, 2022), MODERN, False),
    Entry("Chinmayi", (2002, 2022), MODERN),
    Entry("Haricharan", (2006, 2022), MODERN),
    Entry("Shreya Ghoshal", (2003, 2020), MODERN),
    Entry("Benny Dayal", (2008, 2020), MODERN),
    Entry("Jonita Gandhi", (2015, 2025), MODERN),
    Entry("Dhanush", (2011, 2022), MODERN),
]


def _key(name: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", name.casefold())


_BY_KEY: dict[str, Entry] = {}
for _e in SEED:
    for _n in (_e.name, *_e.aliases):
        _BY_KEY.setdefault(_key(_n), _e)

_SPLIT = re.compile(r"\s*(?:,|&|;|/|\bfeat\b\.?|\bft\b\.?|\band\b)\s*", re.I)


def lookup(artist_name: str | None) -> Entry | None:
    """The seed entry for an artist credit, matching a whole credit first, then each named part."""
    if not artist_name:
        return None
    if (hit := _BY_KEY.get(_key(artist_name))):
        return hit
    for part in _SPLIT.split(artist_name):
        if (hit := _BY_KEY.get(_key(part))):
            return hit
    return None
