# Music Pack (.mpak) Specification

**Version 1.** Changes within version 1 only add optional features. A change that breaks existing files is a new version. The manifest `version` field says which version a file uses.

A Music Pack file (extension `.mpak`) packages one song. It holds the score, the recordings that go with
it (original, backing track, stems), and the sync points that align the score to each recording. The file is a ZIP archive
of ordinary files, so any language can read and write it.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY have the meanings defined in RFC 2119.

## Contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Profiles](#2-profiles)
3. [Container](#3-container)
4. [Manifest](#4-manifest)
5. [Song metadata](#5-song-metadata)
6. [Score](#6-score)
7. [Recordings](#7-recordings)
8. [Stems](#8-stems)
9. [Sync](#9-sync)
10. [Reader requirements](#10-reader-requirements)
11. [Writer requirements and enrichment](#11-writer-requirements-and-enrichment)
12. [Security](#12-security)
13. [Versioning and extensions](#13-versioning-and-extensions)
14. [Copyright, patents, names](#14-copyright-patents-names)

## 1. Goals and non-goals

Goals:

- One file carries everything needed to work with a song: score, recordings, sync, and instrument tunings.
- A file can hold several scores of one song, such as a Guitar Pro file and a PDF, and each is synced to the recordings.
- A score reader can adopt all of the format or only the part it needs (section 2).
- A file written by a simple script (a title and a score) is as valid as a file written by a full application.
- Another tool can improve a file later, for example by adding audio files, without breaking the file.

Non-goals:

- It does not define a new notation format. The score inside is an existing file, stored untouched.
- It does not define playback engines, user interfaces, or library matching.
- It does not require any network service. A reader MUST be able to open a file without network access.

## 2. Profiles

A profile is a subset of this specification that a reader can implement on its own. A reader states which profiles it
supports. A writer SHOULD target the smallest profile that can hold its data.

| Profile | Covers | Sections |
|---|---|---|
| **Core** | Container, manifest, song metadata, the score | 3 to 6 |
| **Playback** | Core, plus recordings, sync points and beat files | 7, 9 |
| **Stems** | Playback, plus stems | 8 |

A Core reader ignores `recordings` and sync files. A Playback reader plays stem recordings as ordinary recordings.

## 3. Container

A `.mpak` file is a ZIP archive. It uses the ISO/IEC 21320 subset of ZIP, plus ZIP64 where needed. The archive has this
layout:

```
manifest.json     the manifest (section 4)
score/<name>      the score files, byte for byte as supplied (a score that uses externalPath has none; section 6),
                  including the files of alternate scores (section 6.3)
audio/<name>      optional audio files
sync/<name>.json  optional sync files (section 9)
beats/<name>.json optional beat files (section 7, "Beat file")
x-<name>/...      optional extension files of one application (section 13.1)
```

Rules:

1. The archive has no `mimetype` entry, and a writer MUST NOT write one. A reader recognizes a file by its `manifest.json`
   (`format` is `mpak`), together with the `.mpak` extension and the media type `application/vnd.mpak+zip`. A file from
   an earlier writer can have a `mimetype` entry. The manifest does not name it (rule 7), so a reader ignores it.
2. `manifest.json` MUST be present. It MUST be UTF-8 JSON with no byte order mark, and at most 1 MiB.
3. Entry names MUST be UTF-8 and use `/` as the separator. A name MUST be relative and MUST NOT contain a `..` segment,
   an empty segment, a backslash, or a control character. Names MUST be unique, also when compared case-insensitively.
4. The compression method MUST be Stored or Deflate. Encryption MUST NOT be used.
5. Audio entries SHOULD be Stored. Audio is already compressed, and a Stored entry lets a reader seek without inflating.
6. A reader MUST NOT depend on entry order. The manifest MUST NOT hold offsets or
   checksums of the archive itself, so that a tool can rewrite the archive. Hashes of file contents are fine.
7. An entry that the manifest does not name is allowed, and readers MUST ignore it. A writer that rewrites a file SHOULD
   keep such entries.

### 3.1 Large files and streaming

A file can hold hours of audio, so this specification sets no size limit of its own.

1. A writer MUST use ZIP64 where the ZIP format requires it: an entry or offset of 4 GiB or more, or 65535 or more
   entries. A reader MUST read ZIP64.
2. A reader MUST be able to open a file without reading its audio. Opening needs only the end of the archive, the
   central directory, the manifest, the score, the sync files, and the beat files. The reader SHOULD read these by
   random access instead of loading the whole archive into memory.
3. A reader MUST take sizes, offsets and checksums from the central directory, and MUST ignore any different value in a
   local header. A writer MAY use data descriptors.
4. A Stored audio entry is a contiguous byte range of the archive. A reader MAY play or copy it from that range without
   inflating or copying it. It MAY skip the CRC-32 check for such an entry, because checking it means reading all of it.
5. A reader that inflates an entry MUST count the output as it inflates and stop at the limits in section 12. It MUST NOT
   use the sizes in the archive for this count.
6. A reader MUST NOT hash audio in order to open a file. It MAY check a `sha256` of an audio source later, on demand or in
   the background.
7. A reader reads the score, the manifest, the sync files, and the beat files whole. A reader MAY refuse a score larger than 256 MiB.

## 4. Manifest

`manifest.json` is a JSON object. Its JSON Schema is `schema/manifest.schema.json`.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `format` | `"mpak"` | yes | Format marker. |
| `version` | integer, `1` | yes | Spec major version. A reader MUST reject a higher value and say so. |
| `id` | string | no | The identity of this pack: a name that stays the same when the pack is edited, copied, or moved between devices and libraries. 1 to 64 of `A-Z a-z 0-9 _ -`. A writer SHOULD use a lowercase UUID: version 4, or version 5 when derived from the primary score (below). See "Pack identity". |
| `createdAt` | string, date-time | no | When the file was created. |
| `generator` | `{ name, version? }` | no | The software that wrote the file. |
| `song` | object | no | Section 5. It can be empty or absent. |
| `scores` | array | yes | One or more scores of the song. The first is the primary score. Section 6. |
| `recordings` | array | no | Section 7. |
| `entries` | object | no | Size and hash of the archive entries that the manifest names by path only (sync files and beat files). See "Integrity". |

Other fields are allowed. A reader MUST ignore a field it does not know. A field that is private to an application SHOULD start with
`x-` (section 13).

### Integrity

A manifest can state how big each file it points to is, and its hash, so that a reader, or a tool that keeps the entries
as separate files, can tell a complete file from a damaged or half-written one.

- `size` is the number of bytes of the file's content (not its compressed size in the archive). It is an optional field
  of a score (section 6) and of a `file` audio source (section 7), next to `sha256`.
- `entries` is an object from an archive path to `{ "size": <integer>, "sha256": "<hex>" }`, both required. It is for the
  entries that the manifest names by path only, which have no field of their own for this: the sync files and the beat files.
  It does not repeat the score and audio files, which carry `size` and `sha256` themselves. An item for a path that the
  archive does not hold is ignored.

```json
"entries": {
  "sync/r1.json": { "size": 1842, "sha256": "..." },
  "beats/r1.json": { "size": 960, "sha256": "..." }
}
```

All of it is optional, and none of it is needed to open a file.

- A reader SHOULD warn when a size or hash that the manifest gives does not match the entry it reads, as for a score's
  `sha256` (sections 10 and 12). It MAY then skip the sync or beat file that failed. It MUST NOT use a `size` from the
  manifest as a limit or to size a buffer, because the manifest is untrusted input (sections 3 and 12): it takes sizes
  from the central directory.
- A reader MUST NOT hash audio in order to open a file (section 3). It MAY compare an audio `size` with the size in the
  central directory, which costs nothing.
- A writer SHOULD write `size` for each score and each `file` source, and an `entries` item for each sync file and each
  beat file.
- A writer MUST keep what it writes true. A writer that changes a sync file, a beat file, or an audio file in an existing
  pack updates its `size` and `sha256`, or removes them (and for a score, section 11, "Changing a score" also applies).

### Pack identity

`id` names the pack, so that a library, a sync service, or a person can tell that two files are the same song at different
moments, without comparing titles. It is not derived from the pack's contents or from the song metadata, because those
change when the pack is edited.

- A writer that creates a pack SHOULD write an `id`. A random UUID (version 4) is the usual choice. A tool that converts
  another source into a pack, and so makes the same pack again from the same input, MAY use the derived `id` below, which
  makes the result repeatable.
- A writer that edits a pack, or writes a copy of it for the same song, MUST keep the `id` it has.
- A writer that makes a pack for a different song out of an existing one (the copy is edited into another song) MUST
  write a new `id`.
- A reader MAY treat two files with the same `id` as the same song. It then merges them as section 6.2 says, and MUST NOT
  overwrite or remove what it already has unless the user asks it to. A file without an `id` is matched by `song.ids`, by
  `title` and `artist`, or by asking the user (section 6.2), and a reader MAY give it an `id` of its own when it stores it.
  A tool that does so, or that uses a derived `id`, derives it as the UUID version 5 (RFC 4122) of the primary score's `sha256` (the
  64 lowercase hex characters, as UTF-8) in the namespace `03924935-9520-4f8c-91cd-ebd5f6cf57c5`, so that two tools that give an `id` to the same file
  choose the same one. For a `sha256` of 64 zeros that is `8980d354-7334-5de0-8804-bb35580aea65`. The tool then stores the `id` and does not derive it again.
- The `id` says nothing about who made the pack and proves nothing. A reader MUST NOT use it for a decision about trust or
  permission.

## 5. Song metadata

`song` is optional, and every field in it is optional.

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Song title. |
| `artist` | string | Performing artist. |
| `composer` | string | Composer, for classical and instrumental pieces. |
| `album` | string | Album or release title. |
| `year` | integer | Year of release. |
| `genre` | string | Genre, as free text. |
| `publisher` | string | Publisher of the song or the arrangement. |
| `trackNumber` | integer | Track number on the release. |
| `mediumNumber` | integer | Disc number. |
| `length` | integer | Length of the song in milliseconds. |
| `ids` | object | External identifiers (below). |

`ids` is an object keyed by service. The values are hints that a reader MAY use to match the song to a library. A reader
MUST NOT require them, and this specification mandates no lookup (section 10).

```json
"ids": {
  "musicbrainz": {
    "recording": "<uuid>",
    "artist": "<uuid>",
    "release": "<uuid>",
    "releaseGroup": "<uuid>"
  },
  "isrc": "USRC17607839"
}
```

Defined keys: `musicbrainz` (object with optional `recording`, `artist`, `release`, `releaseGroup`, each a UUID string;
`releaseGroup` identifies the album across editions and `release` identifies a specific edition) and `isrc`
(string). Other keys are allowed.

If `title` or `artist` is missing and a reader needs a display name, the reader SHOULD use the first of these that
exists:

1. Metadata inside the score file.
2. The score's file name.
3. The name of the `.mpak` file.

## 6. Score

`scores` is an array of one or more items. Each item describes one score of the song. The first item is the **primary
score**: a reader shows it first and uses it where the specification says "the primary score". The order of the other
items is a display order only. Several scores can be in different formats, for example a Guitar Pro file and a PDF, or
two arrangements (section 6.2).

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Identifier, unique among all the scores and alternates of the file (same character rules as recording ids). Sync refers to a score by it (section 9). |
| `label` | string | no | Name for display, such as `"Guitar Pro"` or `"Piano arrangement"`. |
| `path` | string | unless `externalPath` | Archive path of the score file, under `score/`. |
| `externalPath` | string | unless `path` | Relative path to a shared PDF file outside the archive (`pdf` only). |
| `format` | enum | yes | `gp3`, `gp4`, `gp5`, `gp` (Guitar Pro 7 and later), `gpx`, `musicxml` (uncompressed MusicXML), `mxl` (compressed MusicXML), `mscz` (MuseScore), `midi` (Standard MIDI File), `abc` (ABC notation), `alphatex` (alphaTex, `.atex`), `pdf`, `txt`. |
| `sha256` | string | yes | Lowercase hex SHA-256 of the score file's bytes. |
| `size` | integer | no | Size of the score file in bytes. See "Integrity" in section 4. |
| `name` | string | no | The original file name, for display. |
| `pages` | integer | no | Page count of the PDF file, for `pdf`. |
| `startPage` | integer | no | 1-based first page of this song inside a multi-song PDF (`pdf` only). |
| `endPage` | integer | no | 1-based last page of this song inside a multi-song PDF (`pdf` only, `>= startPage`, `<= pages`). |
| `instruments` | object array | no | Instruments the score is for, with their tunings. See below. Informational. |
| `alternates` | array | no | Alternate scores that use this score's sync points. Section 6.3. |

- At least one score is required. A file with only recordings and sync is not valid, because sync points need a score to anchor to.
- A score MUST have either `path` or `externalPath`, and MUST NOT have both. `externalPath` is allowed only when `format`
  is `pdf`.
- Bar and track indices count what the stored score file lists, and the file is stored untouched and pinned by `sha256`,
  so a later version of the score's format cannot change what an index means. A reader reads the file with the rules of
  the format version that wrote it (`gp`, `mscz`).
- A writer MUST store an embedded score file (`path`) exactly as supplied and MUST NOT convert or re-encode it. The one
  exception is a `txt`, `abc`, or `alphatex` score, which MUST be UTF-8. If such a score uses another encoding, the writer converts it
  to UTF-8 and records the hash of the converted file.
- `sha256` identifies the score file that the score's sync anchors (and, for the primary score, the stem track links) were
  written against (for an external PDF, the whole PDF file). If a reader finds a different hash, it SHOULD tell the user that sync points may be wrong, and it
  MUST NOT silently apply track links (section 8).
- `instruments` is for scores that do not carry their own instrument and tuning information, mainly `pdf`, `txt`, and
  `abc`. For a format that carries it, the file wins. For those formats, a writer SHOULD omit `instruments` or make it
  agree with the file. A reader MAY show it to the user, for example "Bass: E A D G, Guitar: drop D, capo 2". It does
  not change how sync or track links work.
  Each entry is an object, and every field is optional:

  | Field | Type | Meaning |
  |---|---|---|
  | `name` | string | A display name, for example `"Lead guitar"`. A reader MAY match it to a track by name, as for `stem.trackName`. |
  | `tuning` | string array | The open strings as pitch names with or without octave numbers, for example `["E2","A2","D3","G3","B3","E4"]` or `["D","A","D","G","B","E"]`. List them in the order the score lists strings, usually lowest first. A re-entrant tuning (ukulele, banjo) keeps its own order. |
  | `capo` | integer | The capo fret, 1 or more. Omit it for no capo. |

  A score for several instruments lists one entry for each instrument that has a tuning worth stating.
- The format decides the anchor type that sync uses (section 9): `gp3`, `gp4`, `gp5`, `gp`, `gpx`, `musicxml`, `mxl`,
  `mscz`, and `alphatex` use `bar`; `midi` uses `tick`; `pdf` uses `pdf`; `txt` and `abc` use `text`.
- The score can be for any instrument. `instruments` can describe any fretted or stringed instrument, and the Guitar Pro
  formats suit guitar, but neither limits what a file can hold.

### 6.1 Multi-song PDFs (`startPage`, `endPage`, and `externalPath`)

A single PDF, such as a songbook, can hold several songs. Each song is its own `.mpak` file, and `startPage` and
`endPage` give its 1-based inclusive page range inside that PDF. Both fields are allowed only when `format` is `pdf`.
When both are present, `endPage` MUST be greater than or equal to `startPage`. When `pages` is also present, both
`startPage` and `endPage` MUST be at most `pages`. When only `startPage` is set, the song runs from `startPage` to the
end of the PDF. When only `endPage` is set, the song runs from page 1 to `endPage`.

The PDF can be stored inside the archive (`path`, under `score/`) or left outside it and referenced by `externalPath`.
With `externalPath`, several `.mpak` files for songs from the same book can share one copy of the PDF instead of
duplicating it in every archive. Rules for `externalPath`:

- `externalPath` follows the same safe relative path rules as archive entry names (section 3): UTF-8, `/` separated, no
  leading `/`, no backslash, no `.`, `..`, or empty segment, and no control characters.
- When a reader opens a `.mpak` file from a directory on disk, it resolves `externalPath` inside that directory (and it MUST
  reject any path that escapes that directory; section 12). A reader with its own library MAY also locate the PDF by the score's `sha256`, or
  ask the user for the file when it is missing.
- `sha256` is still required when `externalPath` is used, and is the SHA-256 of the whole PDF file.

### 6.2 Several scores

A file can hold several scores of one song, for example a Guitar Pro file and a PDF of the same song, or two arrangements.
They need not share a format or a structure. The first is the primary score.

- **Sync is kept per score and recording.** Sync points are written against the bytes of one score, and different
  scores can have different anchor types. A recording therefore has one sync file for each score that it is synced
  to (section 9). A reader MUST NOT apply one score's sync points to another score, except to the alternates of that score
  (section 6.3). A score with no sync data for a recording is shown without a moving position.
- **Scores that keep the same structure.** When a second score is a simplified, transposed or re-engraved copy that lines up
  with a score already in the file, it SHOULD be an alternate of that score (section 6.3). It then needs no sync file of its
  own.
- **The primary score** is the one a reader shows first. Stem track links (section 8) refer to its tracks, and an
  `embedded` source (section 7) is in it unless the source names another score. Moving another score to the front changes
  both of those, but it changes no sync file, because sync is keyed by score `id`.
- **Instruments and metadata** are per score.
- A reader MAY merge a file into a song that it already has. How it finds the song (by the manifest's `id`, by
  `song.ids`, by `title` and `artist`, or by asking the user) is outside this specification (section 10), except that
  two files with the same `id` MAY be treated as one song (section 4, "Pack identity"). It MUST NOT overwrite or remove the
  scores, recordings or sync points it already has unless the user asks it to. A score whose `sha256` matches one it
  already has is the same score, and a reader SHOULD NOT add a duplicate. Two recordings with the same `youtube`
  `videoId`, or the same audio `sha256`, share a source, and a reader MAY store that source once. It MUST keep both
  recordings, with their sync files, unless the two recordings have the same sync points for every score (section 7,
  "One source in several recordings").
- A reader that shows only one score shows the primary score.

### 6.3 Alternate scores

An **alternate** is a score that is derived from another score of the file and keeps its structure, so that the
sync points of that score (its **parent**) are valid for the alternate unchanged. Examples: an easy or simplified arrangement, a version transposed or with
different fingering, a bass-only or vocals-only reduction, a MusicXML export of a Guitar Pro score, a re-engraved
copy. Alternates are listed in the `alternates` array of their parent. Each item has all the fields of a score (section 6) except
`alternates`, so an alternate cannot have alternates of its own. Its `id` and `label` follow the same rules as for a score.


```json
"scores": [
  { "id": "main", "path": "score/song.gp", "format": "gp", "sha256": "...",
    "alternates": [
      { "id": "easy", "label": "Easy", "path": "score/song-easy.gp", "format": "gp", "sha256": "..." },
      { "id": "xml",  "label": "MusicXML export", "path": "score/song.musicxml", "format": "musicxml", "sha256": "..." }
    ] },
  { "id": "pdf", "path": "score/song.pdf", "format": "pdf", "sha256": "..." }
]
```

- **Same sync data.** The file has one set of sync points per recording and parent score, written against the parent
  (section 9). A reader applies those points to the parent's alternates unchanged. An alternate MUST therefore have the
  same anchor type as its parent, and MUST line up with it:
  - For `bar` anchors, bar `n` (with its `occurrence` and `pos`) is the same music in both scores and has the same
    repeat and jump structure.
  - For `tick` anchors, the scores have the same tick resolution and tempo map.
  - For `text` anchors, the scores have the same lines.

  A writer MUST NOT list a score as an alternate when its structure differs, for example when it has a different bar
  count, a re-ordered form, or a different layout. That score is a separate score (section 6.2), with its own sync. A
  `pdf` alternate is valid only when its pages and coordinates match its parent PDF, so it is rarely derivable this way.
- **The parent stays the reference.** The parent is the score that sync is written against. A reader shows the parent
  unless the user picks one of its alternates. Order in `alternates` is a display order only.
- **Files.** Each alternate has `path` or `externalPath` under the same rules as a score (section 6, 6.1), and its
  own `sha256`. A writer stores an embedded alternate byte for byte. An alternate's `sha256` is checked on its own. On a
  mismatch, a reader SHOULD warn and MAY refuse to show that alternate. A mismatch does not affect the parent.
- **Track links.** `stem.track` counts the primary score's tracks (section 8). A reader MUST NOT apply a `stem.track` index to
  an alternate, or to any score other than the primary. It MAY find the track by `stem.trackName` when exactly one track in the alternate has that name.
  Otherwise it mutes nothing.
- **Instruments and metadata** are per alternate. An alternate MAY have different `instruments` (for example drop D), even
  though its bar structure matches.
- A reader that does not know `alternates` ignores it (section 10) and shows only the scores in `scores`.

## 7. Recordings

`recordings` is an ordered array. Each entry is one recording: one performance, in one or more forms (the `sources`).

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique in the file. 1 to 64 of `A-Z a-z 0-9 _ -`. |
| `role` | string | yes | What the recording is (below). |
| `label` | string | no | Display name. |
| `sources` | array | yes | Ordered forms of this recording. May be empty. |
| `sync` | object | no | Archive paths of this recording's sync files, one for each score: a map from a score `id` to a path. Section 9. |
| `syncFrom` | string | no | Id of a recording whose sync points and beat file this one shares, for each score that has no `sync` entry here, and when this recording has no `beats` entry. |
| `syncOffsetMs` | integer | no | Milliseconds added to the points and beats shared through `syncFrom`. May be negative. Section 9. |
| `beats` | string | no | Archive path of this recording's beat file, under `beats/`. One for each recording, not for each score. See "Beat file". |
| `scoreTracks` | object | no | Which tracks of each score the audio has or lacks: a map from a score `id` to `{ "omits": [...] }` or `{ "only": [...] }`. See "Tracks in a recording". |
| `without` | string array | no | Ids of stems (recordings with role `stem`) whose parts are not in this recording's audio. Section 8. |
| `stemOf`, `stem`, `stemsComplete` | | no | Section 8. |

### Roles

`role` is an open vocabulary. Defined values:

- `original`: the released recording of the song.
- `backing`: the song without the part being played.
- `stem`: one part of a mix (section 8).
- `alternate`: another version of the released recording, such as a remaster, a re-recording, or a second video of the same
  song. A reader treats it like `original`, but does not take it as the default over an `original`.
- `solo`: a recording of the part that is played alone, such as an isolated instrument.

Suggested values: `live`, `cover`, `click`, `lesson`. If a reader does not know a role, it shows the `label` and treats
the recording as an ordinary one.

### Tracks in a recording

`scoreTracks` says which tracks of a score are in the audio. The key is a score `id` (primary scores and other scores of
`scores`, not alternates). The value has one of two fields, never both:

- `omits`: indexes of the score's tracks that are **not** in the audio. This is the usual form for `backing`, where the
  audio lacks the part you play.
- `only`: indexes of the score's tracks that are the **only** ones in the audio, as for a `solo`.

An index is 0-based in the order that the score file lists its tracks, as for `stem.track` (section 8). A recording with no
entry for a score has all of that score's tracks, and a reader assumes nothing about them.

The entry MAY also have `names`: the names of those tracks as the score file gives them, in the same order and the same
number as the indexes. It is a check, like `stem.trackName`. If the track at an index has a different name, the reader
ignores the whole entry, because the track order has changed since it was written. A writer that knows the track names
SHOULD write `names`.

A reader MAY use it to mute, hide, or highlight tracks so that the audio and the score agree, for example to play the
score's own sound for the omitted track. It MUST ignore the entry when the score's `sha256` does not match its file, when
the score's format does not list tracks (`pdf`, `txt`, `abc`), when an index is out of range, or when `names` does not match (above). A wrong mute is worse than
none. `label` is for people only: a reader MUST NOT read track names out of it.

```json
{ "id": "v3", "role": "backing", "label": "Backing track (without Drums)",
  "sync": { "main": "sync/v3.json" },
  "scoreTracks": { "main": { "omits": [1], "names": ["Drums"] } }, "sources": [ ... ] }
```

### Sources

A recording lists its forms in `sources`. A reader plays the first source it can play and skips the rest. A reader skips
a source type it does not know. That is not an error. If no source is playable, the reader shows the recording as
unavailable.

Every source has a `type`. A source can also have these optional fields:

- `id`: a name that `derivedFrom` can refer to.
- `offsetMs`: where this source starts on the recording's timeline. The default is 0.
- `durationMs`: the length of the source, in milliseconds.
- `sha256`: the hash of the audio bytes.
- `size`: the size of the audio file in bytes (see "Integrity" in section 4).
- `derivedFrom`: the `id` of another source of the same recording that this one was made from.

| `type` | Extra fields | Meaning |
|---|---|---|
| `file` | `path` (required, under `audio/`), `mime` | An audio file in the archive. |
| `youtube` | `videoId` (required, 11 characters) | A YouTube video, played with the service's own player. |
| `url` | `url` (required, `http` or `https`), `mime` | Audio at a web address. |
| `embedded` | `score` (optional) | Audio carried inside a score file itself, for example the audio track of a Guitar Pro 7 or later (`gp`) file. |
| `external` | none | A recording that exists but has no playable source here. `sha256` and `durationMs` help identify it. |

An `embedded` source has no `path`: the bytes are in a score file, and the reader extracts them with its own code for that
score format. `score` is the `id` of the score that holds them, and defaults to the primary score. It names a score of
`scores`, not an alternate. These rules apply:

- It is defined for the score format `gp`. If the score is any other format, a reader skips it, and a writer MUST NOT write it.
- It is valid only for the exact score file that the score's `sha256` identifies. If the hash does not match, a reader MUST skip
  the source.
- `offsetMs` places the embedded audio on the recording's timeline, like any other source. When the recording has sync
  points (section 9), they apply instead of the score's own sync points. When the recording has no sync points in the
  `.mpak` file, a reader MAY fall back to the sync points stored inside the `gp` file.
- A tool MAY extract the audio into `audio/<name>` and prepend a `file` source to the same recording (or place it before
  the `embedded` source), with `derivedFrom` set to the embedded source's `id` (section 11). The `embedded` source stays,
  so the file still round trips.
- A recording can have only one `embedded` source, because a score file has one audio track. Another recording can use the
  audio of another score.

Other types are allowed. A source of any type MAY appear on any recording, including a stem.

### Default recording

The first recording in `recordings` is the default. A reader uses it first, and a writer puts the recording it wants
used first at the start of the list. There is no separate field for this.

### One source in several recordings

Two recordings MAY list the same source, for example the same YouTube video or the same audio file. A writer does this
when it has more than one set of sync points for one performance, such as points from two people or two tools that differ
slightly. It gives each recording its own `sync` entries, and it SHOULD say in each `label` how they differ, for example
`"Studio version (alternate sync)"`. The recording that the writer wants used first goes first (see "Default recording").

A recording has one sync file for each score (section 9), so alternate sync points are separate recordings, not a second
entry in one `sync` map. A reader SHOULD offer them as choices and MUST NOT merge their points. A reader that stores the
shared source once (section 6.2) keeps every recording that uses it.

Two recordings that share a source and have identical sync points for every score are duplicates, and a writer SHOULD list
only one.

### Timeline

Each recording has one timeline that starts at 0 ms. Sync points (section 9) are positions on that timeline, not on any
one source. If you replace a source with another form of the same recording, the points stay valid. A source that starts
earlier or later than the timeline says so with `offsetMs`.

### Beat file

A beat file says where the beats of one recording fall on its timeline, and where its sections begin. It describes the
recording only, so it names no score and has no anchor type. It is not sync (section 9). A click track, a tapped grid,
and a grid measured from the audio can all be written as one. The recording's `beats` field names it. Its JSON Schema is
`schema/beats.schema.json`.

**Beats and sync answer different questions.** A beat file says *when the beats of the recording are*. A sync file says
*where in the score the recording is*. Neither replaces the other, and a file can have either, both, or neither.

| | Beat file (section 7) | Sync file (section 9) |
|---|---|---|
| Describes | The recording alone | One score against one recording |
| Count | One for each recording | One for each recording and score |
| Depends on the score format | No | Yes (the anchor type) |
| Answers | When is each beat, which beats are downbeats, where do sections start | Where is the playhead in the score at this time |
| Moves the score cursor, turns pages | No | Yes |
| Gives a metronome, count-in, beat-snapped loops, section loops | Yes | No |
| Gives a bar number | Never | For `bar` anchors |
| Needs a score | No | Yes |

What a reader can offer, by what the file holds:

| The file holds | The reader can offer |
|---|---|
| Neither | The score and the recording side by side, with no cursor |
| Sync only | A cursor in the score. A metronome or count-in only from the score's own beats (a score with a beat structure, such as Guitar Pro or MusicXML), placed through the sync points. `pdf` and `text` scores have none. |
| Beats only | A metronome, count-in, beat counter, beat-snapped loops and section loops that follow the recording, for any score format or none. No score cursor. |
| Both | All of the above. |

A beat file matters most for a recording whose score has no beat structure of its own (`pdf`, `txt`, `abc`, and `midi`
without bars) and for a recording that no score is synced to. For a score that does have one, the score and its sync
points already give a reader a click list, so the beat file adds the measured downbeats and tempo, the count-in, and
the named sections. A beat file is never required. A writer that did not measure or receive the beats leaves it out.

```json
{
  "version": 1,
  "recording": "mix",
  "beats": [
    { "timeMs": 1200 },
    { "timeMs": 1700, "downbeat": true },
    { "timeMs": 2200 }
  ],
  "sections": [
    { "name": "Intro", "type": "intro", "timeMs": 1200 },
    { "name": "Verse 1", "type": "verse", "timeMs": 9200 }
  ]
}
```

- `recording` is the id of the recording whose `beats` entry names the file. It MUST equal that id.
- `beats` is an array, sorted by `timeMs`, strictly increasing. It may be empty. Each beat has:
  - `timeMs`: milliseconds on the recording's timeline, 0 or more.
  - `downbeat` (optional): `true` when the beat is the first beat of a bar. The default is `false`. A file in which no
    beat has `downbeat` says nothing about where bars start.
- `sections` (optional) is an array of named parts of the recording, sorted by `timeMs`, strictly increasing. A section
  runs until the next one starts, or to the end of the recording. Each section has:
  - `name`: a name for display, such as `"Verse 1"`.
  - `type` (optional): an open vocabulary. Suggested: `intro`, `verse`, `chorus`, `bridge`, `solo`, `interlude`,
    `outro`. A reader that does not know a `type` shows the `name`.
  - `timeMs`: where the section starts, as for a beat.
- Beats before the music starts, such as a count-in, are ordinary beats. The file has no field for them, and a reader
  that wants the count-in counts the beats before the first section or the first sync point.
- **Resolution.** To find the beat file of recording R:
  1. If R has a `beats` entry, use that file. Its times are already on R's timeline.
  2. Otherwise, if R has `syncFrom`, find the beat file of that recording and add R's `syncOffsetMs` (default 0) to every
     `timeMs`.
  3. Otherwise, if R has `stemOf`, find the beat file of that recording. Add no offset.
  4. Otherwise R has no beat file.

  A chain that returns to a recording it already visited is invalid. A reader drops any beat or section whose `timeMs`
  ends up below 0.
- **Use.** A reader MAY use the beats for a metronome, for a beat counter, for looping, for slowing the audio down on
  beat, and the sections for a section list and for looping a section. A reader MUST NOT derive sync points from a beat
  file, and MUST NOT take a bar number from it. Only a sync file (section 9) aligns a score to a recording.
- **Writers.** A writer writes the beats that it measured or was given. It MUST NOT invent a `downbeat`, and it MUST NOT
  fill a gap in a grid with made-up beats.
- A beat file is at most 8 MiB (section 12).

## 8. Stems

A stem is one part of a mix, such as one instrument. The stems of one split are time-aligned, and a reader plays them
together.

```json
{ "id": "mix",  "role": "original", "stemsComplete": true, "sources": [ ... ] },
{ "id": "gtr1", "role": "stem", "stemOf": "mix", "label": "Lead guitar",
  "stem": { "instrument": "guitar", "track": 0, "trackName": "Lead" }, "sources": [ ... ] }
```

| Field | Meaning |
|---|---|
| `stemOf` | Id of the recording this stem was split from. Only with `role: "stem"`. The stem's audio is time-aligned with that recording (offset 0). Unless the stem has its own `sync`, it uses that recording's sync points. |
| `stem.instrument` | Open vocabulary. Suggested: `guitar`, `bass`, `drums`, `vocals`, `keys`, `other`. |
| `stem.track` | 0-based index into the primary score's track list (formats that list tracks only). |
| `stem.trackName` | Optional. The name of that track, used as a check. |
| `stemsComplete` | On the recording that the stems were split from: `true` when the stems add up to the whole mix. |

- **Guitar-only audio.** If the stem was split from a mix, give it `stemOf`. If there is no mix, leave out `stemOf` and
  give the stem its own sync file.
- **One track per stem.** `stem.track` is a single index. A stem that mixes two tracks has no `track`, and a reader
  mutes nothing for it. A writer that wants per-track muting for those tracks splits them into separate stems.
- **A split of each guitar track.** Use several stems with `instrument: "guitar"`, each with a different `track`.
- **Track links.** `stem.track` is the index of the track in the order that the primary score file lists its tracks. If
  `stem.trackName` is present and the track at that index has a different name, the reader looks for exactly one track
  with that name and uses it. If it finds none or several, it ignores the link and mutes nothing, because a wrong mute is
  worse than no mute. A reader MUST also ignore track links when the primary score's `sha256` does not match its file, and
  when its format is `pdf`, `txt`, or `abc`. Track links apply to the primary score only. For another score a reader MAY
  find the track by `stem.trackName` (section 6.3).
- **Building a backing mix.** If the mix has `stemsComplete: true`, a reader MAY play all its stems except the ones
  linked to the track being played. A separate `backing` recording is then optional.
- **A stem that is not aligned with its parent.** Do not use `stemOf` for it. Give it `role: "stem"` and `stem`, and set
  `syncFrom` to the mix, with a `syncOffsetMs` (section 9).
- **Backing tracks and stems (`without`).** A recording, usually a `backing` one, can list in `without` the ids of the
  stems whose parts its audio lacks. When the recording is the mix with those parts taken out, a reader MAY offer each
  listed stem as an addition, and play the recording and the chosen stems together, each with its own level. This gives
  a backing track for a player who wants to hear one of several parts of an instrument, with no full mix in the file.
  Rules:
  - Every id MUST name another recording of the file whose role is `stem`. An id MUST NOT repeat.
  - A listed stem MUST be time-aligned with the recording at offset 0: the two are played from the same position of
    their sources, so the stem's audio and the recording's audio line up when started together. A writer MUST NOT list a
    stem that would need an offset. A recording whose audio starts at another time than its stems' (for example with a
    count-in, when the stems have none) has no `without`.
  - `without` is about the audio. It does not say which tracks of a score are missing, which `scoreTracks` does
    (section 7). A recording MAY have both.
  - A reader that does not know `without` plays the recording as it is.
- **Stems with no mix.** If the file has stems but no recording that they were split from, and the first
  recording is one of those stems, the default is all of those stems played together.
- The stems of one split share one timeline and one duration.

## 9. Sync

A sync file aligns one score to one recording. It is a JSON file under `sync/` (schema: `schema/sync.schema.json`). It is
not a beat grid: the beats and sections of a recording, which do not depend on any score, are a beat file (section 7,
"Beat file"). The
recording's `sync` field refers to it, under the `id` of the score:

```json
{ "id": "r1", "role": "original", "sources": [ ... ],
  "sync": { "main": "sync/r1-main.json", "pdf": "sync/r1-pdf.json" } }
```

```json
{
  "version": 1,
  "recording": "r1",
  "score": "main",
  "anchorType": "bar",
  "updatedAt": "2026-11-14T12:00:00Z",
  "points": [
    { "timeMs": 0,     "bar": 0, "occurrence": 0, "pos": 0,   "source": "manual" },
    { "timeMs": 2150,  "bar": 1, "occurrence": 0, "pos": 0,   "source": "tap" }
  ]
}
```

- `recording` is the id of the recording that the points belong to, and `score` is the id of the score that they are written
  against. Both MUST equal the ones that the manifest's `sync` entry gives. `score` names a score of `scores`, not an
  alternate.
- `anchorType` MUST match the format of that score (section 6). The points also apply to the score's alternates
  (section 6.3).
- A point MAY carry `x-` fields. A reader ignores any field of a point that it does not know.
- `points` MUST be sorted by `timeMs`, strictly increasing. Each point has:
  - `timeMs`: milliseconds on the recording's timeline, 0 or more.
  - `source` (optional): `tap`, `manual`, or `auto`. The default is `manual`.
  - `id` (optional).
  - the anchor fields for the anchor type, described below.
- A recording with no sync file for a score, no `syncFrom`, and no `stemOf` has no sync data for that score. That is valid, and the score and recording
  still travel together.
- **Resolution.** To find the sync points of recording R for score S:
  1. If R has a `sync` entry for S, use that file. Its points are already on R's timeline.
  2. Otherwise, if R has `syncFrom`, find the points of that recording for S and add R's `syncOffsetMs` (default 0) to each
     `timeMs`.
  3. Otherwise, if R has `stemOf`, find the points of that recording for S. Add no offset.
  4. Otherwise R has no sync data for S.

  Each step can lead to another recording, and the offsets along the chain add up. The chain is followed for one score at
  a time, so R can have its own file for one score and inherit the points for another. A chain that returns to a
  recording it already visited is invalid. A reader drops any point whose `timeMs` ends up below 0.
- **`syncOffsetMs`.** Use it when a recording has the same tempo and structure as another but starts earlier or later,
  for example a backing track with a count-in. A positive value means the music starts later than in the recording
  that it shares points with. `syncOffsetMs` MUST NOT appear without `syncFrom`. It applies only to the scores for which R has no `sync` entry. It applies in the same way to the beat file that R shares through `syncFrom` (section 7, "Beat file").
- **What can be shared.** Sharing assumes the same structure and tempo. A recording with a different arrangement or
  tempo, such as a live version, needs its own sync files. A sync file belongs to one recording and one score, because its
  `recording` and `score` fields MUST equal the ones in the manifest. Two entries cannot point at the same file. Use
  `syncFrom` instead.
- **Exact timing.** A reader that does not know `syncOffsetMs` ignores it and places the cursor too early or too late.
  If exact timing matters, a writer SHOULD give the recording its own sync files.
- Before the first point and after the last, a reader holds the first or last position. It MAY extrapolate instead.

### 9.1 Anchor type `bar` (Guitar Pro, MusicXML, MuseScore, and alphaTex scores)

| Field | Type | Meaning |
|---|---|---|
| `bar` | integer ≥ 0 | 0-based index of the bar in the score's master bar list, which holds the bars in the order that the file lists them, with repeats not expanded. |
| `occurrence` | integer ≥ 0 | Which pass through that bar, counted in playback order. `0` is the first time the bar is played, and a bar inside a repeat has `occurrence` 1 on its second pass. The default is 0. |
| `pos` | number, 0 to 1 | Position inside the bar, as a fraction of its length. The default is 0. |

Points MUST NOT go backwards in playback order. Between two points, a reader SHOULD interpolate in beats using the
score's tempo map. If the score has no tempo map, the reader SHOULD interpolate linearly in time.

The master bar list of each format is:

- Guitar Pro (`gp3`, `gp4`, `gp5`, `gp`, `gpx`): the score's master bars.
- MusicXML (`musicxml`, `mxl`): the `<measure>` elements of the first `<part>`, in document order. Ignore the `number`
  attribute: it can repeat, skip, or be non-numeric (pickup bars, endings). For `mxl`, use the root file that the
  archive's `META-INF/container.xml` names.
- MuseScore (`mscz`): the score's measures in the order that MuseScore lists them.
- alphaTex (`alphatex`): the master bars of the source. Bar `n` is the n-th bar of every staff, and a bar ends at a `|` or
  at the next bar metadata tag, as the alphaTex syntax defines. The number of bars is the largest bar count of any staff.
  A staff with fewer bars counts as having empty bars at the end. Ignore the printed bar numbers (`\ac`, `\barNumber`),
  and do not expand repeats (`\ro`, `\rc`, `\ae`). The file MAY contain its own `\sync` points. A reader ignores them
  and uses the sync file, as it does for the sync points inside a `gp` file (section 7).

### 9.2 Anchor type `pdf`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `page` | integer ≥ 1 | yes | 1-based page number in the PDF file (when the score's `startPage` and `endPage` are set, `page` is between `startPage` and `endPage` inclusive, not renumbered from 1). |
| `x` | number, 0 to 1 | with `y` | Horizontal position, as a fraction of the page width. |
| `y` | number, 0 to 1 | with `x` | Vertical position, as a fraction of the page height. |

- A point has either both `x` and `y`, or neither. A point with only `page` is a **page anchor**: the playhead is
  somewhere on that page, and a reader turns to the page. A point with `x` and `y` is a **position anchor**.
- `x` and `y` are measured on the page's CropBox (its MediaBox if there is none), after applying the page's `/Rotate`,
  with the origin at the top left. They do not depend on resolution or zoom.
- A position anchor marks where the playhead is, typically at the start of a bar or of a line of music.
- A writer that cannot tell where on the page the playhead is MUST write a page anchor, and MUST NOT make up `x` and `y`.
- A file MAY mix page anchors and position anchors.
- **Order and repeats.** Points are ordered by `timeMs`, not by position. A point may name an earlier place in the score than
  the point before it. That is a backward jump, and it means the music repeats: a repeat sign, a D.S., a second verse on the
  first page. A backward jump is not an error. Places are compared in reading order: page, then `y`, then `x`. A page
  anchor counts as the top of its page.
- **Between points.** A reader moves from one point to the next as follows. If the next point is a backward jump, or is on
  another page, the reader holds the earlier point until the next one. Otherwise, if both points are position anchors on
  the same page, the reader MAY interpolate. In every other case it holds.
- A writer SHOULD set the score's `pages`. Anchors are valid only for the exact file that the score's `sha256` identifies.

### 9.3 Anchor type `text`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `line` | integer ≥ 0 | yes | 0-based line number. |
| `col` | integer ≥ 0 | no | 0-based column, counted in Unicode code points. |

- Count lines and columns on the decoded text of the score file (`txt` or `abc`). To decode it, read it as UTF-8, remove a
  leading byte order mark, and replace each CRLF and each CR with LF. Columns count Unicode code points, not UTF-16 units
  or bytes.
- `line` identifies a system (for `abc`, a line of music in the source). A writer SHOULD use the line of the system's top
  string row. A reader SHOULD accept any line within a block of consecutive non-empty lines and treat it as that block.
- A point without `col` is a **block anchor**: the playhead is somewhere in that block, and the reader shows the block. A
  point with `col` is a **column anchor**. In ASCII tab the string rows of a system line up, so `col` is the playhead
  column for the whole system. In `abc`, `col` is a position in the source line, which is only approximate for the music.
- A writer that knows the column of the bar or beat it is anchoring SHOULD write `col`. A writer that knows only the block
  MUST write a block anchor, and MUST NOT make up a `col`. A writer that has a finer position than a block but cannot
  express it as a column loses that detail. It MAY keep the detail in `x-` fields on the point, which other readers
  ignore.
- **Order and repeats.** As for `pdf`, points are ordered by `timeMs`. A point may name an earlier block than the point
  before it, or an earlier column in the same block. That is a backward jump and means the music repeats. Places are
  compared by `line`, then `col`. A block anchor counts as the start of its block.
- **Between points.** If the next point is a backward jump, or is in another block, the reader holds the earlier point
  until the next one. Otherwise, if both points are column anchors in the same block, the reader MAY interpolate. In every
  other case it holds.

### 9.4 Anchor type `tick` (MIDI scores)

| Field | Type | Required | Meaning |
|---|---|---|---|
| `tick` | integer ≥ 0 | yes | Position in MIDI ticks from the start of the file, in the file's own time division. |

- A Standard MIDI File has no bars and no repeats. A point names a tick, and a reader can derive bars from the file's
  time signature events when it wants to show them.
- Points MUST NOT go backwards: `tick` MUST be greater than or equal to the previous point's `tick`.
- Between two points, a reader SHOULD interpolate in ticks using the file's tempo map. If the file has none, it SHOULD
  interpolate linearly in time.
- Files that use SMPTE time division have no ticks per beat. A writer MAY still use `tick` for them, counting ticks as
  the file defines them.

## 10. Reader requirements

A reader:

1. MUST open a file with no network access, and MUST NOT make a network request in order to open one.
2. MUST NOT fetch a `url` source, or start a `youtube` source, until the user asks to play that recording.
3. MUST ignore fields, entries, roles, sources and `ids` keys it does not know.
4. MUST reject `version` greater than it supports, with a message saying the file needs a newer reader.
5. MUST treat everything inside the archive as untrusted input (section 12).
6. SHOULD warn when a score's `sha256` (or an alternate's) does not match the file, and likewise when a `size` or an `entries`
   item (section 4, "Integrity") does not match.
7. SHOULD NOT fail on a missing optional part. A file with only a score is a valid file.

Library matching, merging a file into a song (section 6.2), MusicBrainz lookups, and similar
enrichment are application features. They are outside this specification. A reader MAY use the manifest's `id` and `song.ids` for them.

## 11. Writer requirements and enrichment

A writer:

1. MUST follow section 3.
2. MUST write the manifest fields marked required.
3. MUST write a valid sync file for each recording and score that it gives sync points to.
4. MUST store an embedded score file (a score's `path`) byte for byte (a `txt`, `abc`, or `alphatex` score as UTF-8).
5. SHOULD write `generator`.
6. SHOULD write audio entries Stored, and MUST use ZIP64 where section 3.1 requires it.
7. SHOULD write a file in one pass over its audio, without holding the audio in memory.
8. SHOULD write `size` for each score and `file` source and an `entries` item for each sync and beat file, and MUST keep them
   true when it changes one of those files (section 4, "Integrity").
9. SHOULD write `id`, MUST keep the `id` of a pack it edits or copies for the same song, and MUST write a new `id` for a pack
   of a different song (section 4, "Pack identity").

### Changing a score

`sha256` marks the exact bytes that a score's sync anchors were written against (section 6), so a tool that replaces or
edits a score file in an existing pack has to keep that mark true. A writer that does this:

1. MUST update the score's `sha256` (and `pages`, for a PDF) to match the new file.
2. MUST then either confirm that the score's sync points still apply, or remove them. A writer MUST NOT update `sha256`
   without making that decision.
   - The points still apply when the change keeps the structure that the anchors name: the same bars with the same
     repeats and jumps, the same pages, the same lines.
   - They do not apply when the change adds or removes bars, reflows a page, or reorders the form.
3. MUST apply the same rule to an alternate (section 6.3). An alternate has its own `sha256`, and it stays valid for the
   primary score's sync only while it still lines up with that score. If an edit to a score breaks that, the alternate
   is no longer an alternate and the writer MUST remove it from `alternates`, or turn it into a score of its own.
4. MUST NOT apply `stem.track` links to a changed primary score unless the track order is unchanged.
5. MUST update or remove each recording's `scoreTracks` entry for a changed score when the edit adds, removes, or reorders
   tracks, the same as for item 4. An entry whose `names` no longer match is ignored by readers, but a writer MUST NOT
   rely on that.

A reader or editor that keeps sync points outside the file SHOULD key them by the score's `sha256`, and MAY carry them to
a new hash only when the user, or the tool that made the edit, says the structure is unchanged. A different hash does
not by itself show that the points are wrong, which is why section 10 asks a reader to warn and not to refuse.

### Enrichment

A file is valid if it refers to audio only through `youtube` or `url` sources and holds no audio files. Another tool can
improve such a file:

1. Add `audio/<name>` to the archive.
2. Prepend a `file` source to the same recording (or insert it before the source that the audio was made from). Set
   `derivedFrom` to the `id` of that source. If the audio was trimmed or padded, set `offsetMs` so that the existing sync
   points stay valid.
3. Leave the rest of the manifest and the sync files unchanged. Keep unknown fields and `x-` fields.

This specification defines only the layout of the data. It does not say how to obtain audio. Copying audio from a
service can breach that service's terms and the rights of the people who made the recording. The tool's author and its
users decide whether a tool does that (section 14).

## 12. Security

A reader MUST protect against:

- **Path traversal (zip slip).** Reject entries (and every `externalPath`) that break the name rules in section 3. When you
  extract an entry to disk, resolve its path inside a directory of your own choosing. When you resolve an `externalPath`,
  resolve it inside the directory that contains the `.mpak` file. Do not use a path from the archive or manifest as it is.
- **Decompression bombs.** Reject the archive, or stop reading, in any of these cases: an entry inflates to more than 100
  times its stored size, the manifest is over 1 MiB, a sync file or a beat file is over 8 MiB, or the archive has more than 1000
  entries. A reader MAY use higher limits for `audio/` entries. A reader counts inflation on the output as it is produced (section 3.1).
- **Duplicate and overlapping entries.** Reject archives whose central directory has duplicate names or overlapping data.
- **Active content.** A PDF can contain scripts and links, and an audio file can be malformed. Open both with the same
  precautions as for a file from the internet.
- **Remote content.** `url` and `youtube` sources load third-party content. Load them only when the user asks (section 10),
  and prefer `https`. An `http` source is not encrypted or authenticated, so a reader SHOULD tell the user before it loads
  one, and MAY refuse it.
- **Hash mismatch.** A `sha256` that does not match is a warning, not proof of tampering. A hash is not a signature, and
  it does not show who wrote the file.

## 13. Versioning and extensions

- `version` is the major version. A change that older readers can ignore does not change it. Examples are a new optional
  field, role, source type, or anchor field. A change that older readers cannot ignore changes it.
- Readers ignore what they do not know, so writers can add fields at any time.
- A reader that rewrites a file SHOULD keep unknown fields and `x-` fields, and unknown archive entries.

### 13.1 Extensions

A file MAY carry data that this specification does not define. Extensions let an application keep its own data in the
file without a new version and without breaking other readers.

- **Extension fields.** Any JSON object in `manifest.json` or in a sync file MAY have extra fields. This covers the
  manifest itself and `song`, scores, recordings, sources, `stem`, sync files and sync points. The name of an extension
  field MUST start with `x-` followed by a short name for the application or vendor, for example `x-myapp-color`. This
  specification will not define any field that starts with `x-`. A field without the `x-` prefix that this
  specification does not define is reserved for later versions, and a writer SHOULD NOT use one.
- **Extension files.** An application MAY add archive entries under a directory named `x-<name>/`, where `<name>` is the
  same short name, for example `x-myapp/waveform.bin`. The entry names follow section 3, and rule 7 of section 3 applies:
  readers ignore them. The manifest MAY point to them from an extension field.
- **Open vocabularies.** Where this specification says a vocabulary is open (`role`, `stem.instrument`, source `type`), an
  application MAY use values of its own. A reader that does not know a value follows the rule given for that field. Use
  a name that is unlikely to clash, such as `x-myapp-loop`. The closed lists (`format` of a score and `anchorType`) are
  extended only by a later version of this specification.
- **What an extension MUST NOT do.** It MUST NOT change the meaning of a defined field, and a file MUST remain correct
  for a reader that ignores every extension. A change that readers cannot safely ignore is a new `version`, not an
  extension.
- **Readers.** A reader MUST ignore extension fields, entries and values that it does not understand, and MUST NOT
  reject a file because of them. It MUST still apply the limits of section 12 to extension entries.
- **Hashes.** An application MUST NOT put a hash or an offset of the archive itself in an extension (section 3, rule 6).
  Hashes of file contents are fine.

## 14. Copyright, patents, names

- **Copyright.** A `.mpak` file can contain a score and recordings that belong to other people. This specification grants
  no right to them. Writers and distributors are responsible for having the right to include what they include. A file
  can refer to a recording (`youtube`, `url`, `external`) instead of carrying it. A writer SHOULD do that when it does
  not hold the rights to the audio.
- **Patents.** The authors will not assert patent claims against an implementation of this specification as published.
- **Names.** "Music Pack" and the `.mpak` extension may be used freely to describe files and software that follow
  this specification.
- **Media type.** This specification uses `application/vnd.mpak+zip` provisionally. The type is not registered.
