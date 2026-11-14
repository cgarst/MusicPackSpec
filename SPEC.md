# Multi-Track Tab (.mtab) Specification

**Version 1.** Changes within version 1 only add optional things. A change that breaks existing files is a new version, and the manifest `version` field says which one a file uses.

A Multi-Track Tab file (extension `.mtab`) packages one song for practice. It holds the tab, the recordings that go with
it (original, backing track, stems), and the sync points that align the tab to each recording. The file is a ZIP archive
of ordinary files, so any language can read and write it.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in RFC 2119.

## Contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Profiles](#2-profiles)
3. [Container](#3-container)
4. [Manifest](#4-manifest)
5. [Song metadata](#5-song-metadata)
6. [Tab](#6-tab)
7. [Recordings](#7-recordings)
8. [Stems](#8-stems)
9. [Sync](#9-sync)
10. [Reader requirements](#10-reader-requirements)
11. [Writer requirements and enrichment](#11-writer-requirements-and-enrichment)
12. [Security](#12-security)
13. [Versioning and extensions](#13-versioning-and-extensions)
14. [Copyright, patents, names](#14-copyright-patents-names)
15. [Open questions](#15-open-questions)

## 1. Goals and non-goals

Goals:

- One file carries everything needed to practice a song: tab, recordings, sync, and tuning.
- Any tab reader can adopt all of it or only the part it needs (see Profiles).
- A file written by a simple script (a title and a tab) is as valid as one written by a full application.
- Another tool can improve a file later, for example by adding audio files, without breaking it.

Non-goals:

- It does not define a new tab or notation format. The tab inside is an existing file, stored untouched.
- It does not define playback engines, user interfaces, or library matching.
- It does not put several tabs in one file. A song with several tabs is several files (section 6.1).
- It does not require any network service. A reader MUST be able to open a file without network access.

## 2. Profiles

A profile is a subset of this specification that a reader can implement on its own. A reader states which profiles it
supports. A writer SHOULD target the smallest profile that holds its data.

| Profile | Covers | Sections |
|---|---|---|
| **Core** | Container, manifest, song metadata, the tab | 3 to 6 |
| **Playback** | Core, plus recordings and sync points | 7, 9 |
| **Stems** | Playback, plus stems | 8 |

A Core reader ignores `recordings` and sync files. A Playback reader plays stem recordings as ordinary recordings.

## 3. Container

A `.mtab` file is a ZIP archive. It uses the ISO/IEC 21320 subset of ZIP, plus ZIP64 where needed. The archive has this
layout:

```
mimetype          the ASCII bytes application/vnd.mtab+zip   (first entry, stored)
manifest.json     the manifest (section 4)
tab/<name>        the tab file, byte for byte as supplied (omitted when tab.externalPath is used; section 6)
audio/<name>      optional audio files
sync/<name>.json  optional sync files (section 9)
```

Rules:

1. The first entry MUST be `mimetype`. It MUST be stored without compression, have no extra field, and contain exactly
   `application/vnd.mtab+zip` with no trailing newline. A reader MAY use it to identify a file without parsing the
   archive.
2. `manifest.json` MUST be present. It MUST be UTF-8 JSON with no byte order mark, and at most 1 MiB.
3. Entry names MUST be UTF-8 and use `/` as the separator. A name MUST be relative and MUST NOT contain a `..` segment,
   an empty segment, a backslash, or a control character. Names MUST be unique, also when compared case-insensitively.
4. The compression method MUST be Stored or Deflate. Encryption MUST NOT be used.
5. Audio entries SHOULD be Stored. Audio is already compressed, and a Stored entry lets a reader seek without inflating.
6. A reader MUST NOT depend on entry order, except that `mimetype` comes first. The manifest MUST NOT hold offsets or
   checksums of the archive itself. (Hashes of file contents are fine.) This lets a tool rewrite the archive.
7. An entry that the manifest does not name is allowed, and readers MUST ignore it. A writer that rewrites a file SHOULD
   keep such entries.

### 3.1 Large files and streaming

A file can hold hours of audio, so this specification sets no size limit of its own.

1. A writer MUST use ZIP64 where the ZIP format requires it: an entry or offset of 4 GiB or more, or 65535 or more
   entries. A reader MUST read ZIP64.
2. A reader MUST be able to open a file without reading its audio. Opening needs only the end of the archive, the
   central directory, the `mimetype` entry, the manifest, the tab and the sync files. The reader SHOULD read these by
   random access, not load the whole archive into memory.
3. A reader MUST take sizes, offsets and checksums from the central directory, and MUST ignore any different value in a
   local header. A writer MAY use data descriptors for entries other than `mimetype`.
4. A Stored audio entry is a contiguous byte range of the archive. A reader MAY play or copy it from that range without
   inflating or copying it. It MAY skip the CRC-32 check for such an entry, because checking it means reading all of it.
5. A reader that inflates an entry MUST count the output as it goes and stop at the limits in section 12. It MUST NOT
   trust the sizes in the archive for that.
6. A reader MUST NOT hash audio in order to open a file. It MAY check a `sha256` of an audio source later, on demand or in
   the background.
7. The tab, the manifest and the sync files are read whole. A reader MAY refuse a tab larger than 256 MiB.

## 4. Manifest

`manifest.json` is a JSON object. Its JSON Schema is `schema/manifest.schema.json`.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `format` | `"mtab"` | yes | Format marker. |
| `version` | integer, `1` | yes | Spec major version. A reader MUST reject a higher value and say so. |
| `createdAt` | string, date-time | no | When the file was created. |
| `generator` | `{ name, version? }` | no | The software that wrote the file. |
| `song` | object | no | Section 5. May be empty or absent. |
| `tab` | object | yes | Section 6. |
| `recordings` | array | no | Section 7. |
| `defaultRecording` | string | no | Id of the recording to use first. |

Other fields are allowed. A reader MUST ignore a field it does not know. Application-private fields SHOULD start with
`x-` (section 13).

## 5. Song metadata

`song` is optional, and every field in it is optional.

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Song title. |
| `artist` | string | Performing artist. |
| `composer` | string | Composer, for classical and instrumental pieces. |
| `album` | string | Album or release title. |
| `year` | integer | Year of release. |
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
exists: metadata inside the tab file, the tab's file name, the name of the `.mtab` file.

## 6. Tab

`tab` describes the one tab in the file.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `path` | string | unless `externalPath` | Archive path of the tab file, under `tab/`. |
| `externalPath` | string | unless `path` | Relative path to a shared PDF file outside the archive (`pdf` only). |
| `format` | enum | yes | `gp3`, `gp4`, `gp5`, `gp` (Guitar Pro 7 and later), `gpx`, `pdf`, `txt`. |
| `sha256` | string | yes | Lowercase hex SHA-256 of the tab file's bytes. |
| `name` | string | no | The original file name, for display. |
| `pages` | integer | no | Page count of the PDF file, for `pdf`. |
| `startPage` | integer | no | 1-based first page of this song inside a multi-song PDF (`pdf` only). |
| `endPage` | integer | no | 1-based last page of this song inside a multi-song PDF (`pdf` only, `>= startPage`, `<= pages`). |
| `tuning` | string array | no | Tuning, lowest string first, as pitch names with or without octave numbers, for example `["E2","A2","D3","G3","B3","E4"]` or `["D","A","D","G","B","E"]`. |

- `tab` MUST have either `path` or `externalPath`, and MUST NOT have both. `externalPath` is allowed only when `format`
  is `pdf`.
- A writer MUST store an embedded tab file (`path`) exactly as supplied and MUST NOT convert or re-encode it. The one
  exception is a `txt` tab, which MUST be UTF-8. A writer converts any other encoding and records the hash of the
  converted file.
- `sha256` identifies the tab file that the sync anchors and stem track links were written against (for an external PDF,
  the whole PDF file). If a reader finds a different hash, it SHOULD tell the user that sync points may be wrong. It
  MUST NOT silently apply track links (section 8).
- `tuning` is for tabs that do not carry their own, mainly `pdf` and `txt`. For score formats, the tuning in the file
  wins. A writer SHOULD omit `tuning` for those formats or make it agree with the file.
- The format decides the anchor type that sync uses (section 9): `gp3`, `gp4`, `gp5`, `gp`, and `gpx` use `bar`; `pdf`
  uses `pdf`; `txt` uses `text`.

### 6.1 Multi-song PDFs (`startPage`, `endPage`, and `externalPath`)

A single PDF, such as a songbook, can hold several songs. Each song is its own `.mtab` file, and `startPage` and
`endPage` give its 1-based inclusive page range inside that PDF. Both fields are allowed only when `format` is `pdf`.
When both are present, `endPage` MUST be greater than or equal to `startPage`. When `pages` is also present, both
`startPage` and `endPage` MUST be at most `pages`. When only `startPage` is set, the song runs from `startPage` to the
end of the PDF; when only `endPage` is set, it runs from page 1 to `endPage`.

The PDF itself may either be stored inside the archive (`path`, under `tab/`) or left outside the archive and referenced
by `externalPath`, so that several `.mtab` files for songs from the same book can share one copy of the PDF instead of
duplicating it in every archive:

- `externalPath` follows the same safe relative path rules as archive entry names (section 3): UTF-8, `/` separated, no
  leading `/`, no backslash, no `.`, `..`, or empty segment, and no control characters.
- When a reader opens a `.mtab` file from a directory on disk, it resolves `externalPath` inside that directory (and MUST
  reject any path that escapes it; section 12). A reader with its own library MAY also locate the PDF by `tab.sha256`, or
  ask the user for the file when it is missing.
- `tab.sha256` is still required when `externalPath` is used, and is the SHA-256 of the whole PDF file.

### 6.2 One tab per file, and variations

A file holds exactly one tab. A song with several tabs, for example a Guitar Pro file and a PDF of the same song, or two
arrangements, is several `.mtab` files. Each one is a **variation** of the song. This specification does not define a
container for a set of variations.

A reader MAY import a file as another variation of a song that it already has. How it finds that song (by `song.ids`, by
`title` and `artist`, or by asking the user) is outside this specification (section 10). When it does:

1. The file's tab, recordings and sync stay together as one variation. Sync points belong to the tab that `tab.sha256`
   identifies and MUST NOT be applied to another variation, even of the same song, because their anchors are written
   against different tab bytes and may have different anchor types.
2. The reader MUST NOT overwrite or remove the sync points, recordings or tab of a variation it already has, unless the
   user asks it to. A file whose `tab.sha256` matches an existing variation is the same variation: the reader SHOULD NOT
   add a duplicate, and MAY offer to add the file's recordings and sync points to it.
3. Variations MAY share a recording. Two recordings with the same `youtube` `videoId`, or the same audio `sha256`, are the
   same recording, and a reader MAY store it once. Sync is still kept per variation.
4. A file holds one variation, so an export of a song holds the data of one tab. The recordings, sync points and tab of the
   song's other variations are not in it. A tool that exports several variations writes one file for each, and SHOULD put
   the same `song` metadata in each, so that a reader can match them.


`recordings` is an ordered array. Each entry is one recording: one performance, in one or more forms (the `sources`).

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique in the file. 1 to 64 of `A-Z a-z 0-9 _ -`. |
| `role` | string | yes | What the recording is (below). |
| `label` | string | no | Display name. |
| `sources` | array | yes | Ordered forms of this recording. May be empty. |
| `sync` | string | no | Archive path of this recording's sync file. |
| `syncFrom` | string | no | Id of a recording whose sync points this one shares. |
| `syncOffsetMs` | integer | no | Milliseconds added to the points shared through `syncFrom`. May be negative. Section 9. |
| `stemOf`, `stem`, `stemsComplete` | | no | Section 8. |

### Roles

`role` is an open vocabulary. Defined values:

- `original`: the released recording of the song.
- `backing`: the song without the part being practised.
- `stem`: one part of a mix (section 8).

Suggested values: `live`, `cover`, `click`, `lesson`. If a reader does not know a role, it shows the `label` and treats
the recording as an ordinary one.

### Sources

A recording lists its forms in `sources`. A reader plays the first source it can play and skips the rest. A reader skips
a source type it does not know, and that is not an error. If no source is playable, the reader shows the recording as
unavailable.

Every source has a `type`. It can also have these optional fields:

- `id`: a name that `derivedFrom` can refer to.
- `offsetMs`: where this source starts on the recording's timeline. The default is 0.
- `durationMs`: the length of the source.
- `sha256`: the hash of the audio bytes.
- `derivedFrom`: the `id` of another source of the same recording that this one was made from.

| `type` | Extra fields | Meaning |
|---|---|---|
| `file` | `path` (required, under `audio/`), `mime` | An audio file in the archive. |
| `youtube` | `videoId` (required, 11 characters) | A YouTube video, played with the service's own player. |
| `url` | `url` (required, `https`), `mime` | Audio at a web address. |
| `embedded` | none | Audio carried inside the tab file itself, for example the audio track of a Guitar Pro 7 or later (`gp`) file. |
| `external` | none | A recording that exists but has no playable source here. `sha256` and `durationMs` help identify it. |

An `embedded` source has no `path`: the bytes are in the tab file that `tab.path` names, and the reader extracts them
with its own code for that tab format. Rules:

- It is defined for the tab format `gp`. For any other tab format a reader skips it, and a writer MUST NOT write it.
- It is valid only for the exact tab file that `tab.sha256` identifies. If the hash does not match, a reader MUST skip
  the source.
- `offsetMs` places the embedded audio on the recording's timeline, like any other source. When the recording has sync
  points (section 9), they apply instead of the tab's own sync points. When the recording has no sync points in the
  `.mtab` file, a reader MAY fall back to the sync points stored inside the `gp` file.
- A tool MAY extract the audio into `audio/<name>` and prepend a `file` source to the same recording (or place it before
  the `embedded` source), with `derivedFrom` set to the embedded source's `id` (section 11). The `embedded` source stays,
  so the file still round trips.
- A recording can have only one `embedded` source, because a tab file has one audio track.

Other types are allowed. A source of any type MAY appear on any recording, including a stem.

### Default recording

`defaultRecording` names the recording to use first. If it is missing, or names a recording that does not exist, a reader
uses the first recording with the role `original`. If there is none, it uses the first recording in the list.

### Timeline

Each recording has one timeline that starts at 0 ms. Sync points (section 9) are positions on that timeline, not on any
one source. If you replace a source with another form of the same recording, the points stay valid. A source that starts
early or late relative to the timeline says so with `offsetMs`.

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
| `stem.track` | 0-based index into the tab's track list (score formats only). |
| `stem.trackName` | Optional. The name of that track, used as a check. |
| `stemsComplete` | On the recording that the stems were split from: `true` when the stems add up to the whole mix. |

- **Guitar-only audio.** If the stem was split from a mix, give it `stemOf`. If there is no mix, leave out `stemOf` and
  give the stem its own sync file.
- **A split of each guitar track.** Use several stems with `instrument: "guitar"`, each with a different `track`.
- **Track links.** `stem.track` is the index of the track in the order that the tab file lists its tracks. If
  `stem.trackName` is present and the track at that index has a different name, the reader looks for exactly one track
  with that name and uses it. If it finds none or several, it ignores the link and mutes nothing, because a wrong mute is
  worse than no mute. A reader MUST also ignore track links when the tab's `sha256` does not match the tab file, and
  when the tab format is `pdf` or `txt`.
- **Building a backing mix.** If the mix has `stemsComplete: true`, a reader MAY play all its stems except the ones
  linked to the track being practiced. A separate `backing` recording is then optional.
- **A stem that is not aligned with its parent.** Do not use `stemOf` for it. Give it `role: "stem"` and `stem`, and set
  `syncFrom` to the mix with a `syncOffsetMs` (section 9).
- **Stems with no mix.** Suppose the file has stems but no recording that they were split from, and `defaultRecording`
  does not name one. Then the default is all of those stems played together.
- The stems of one split share one timeline and one duration.

## 9. Sync

A sync file aligns the tab to one recording. It is a JSON file under `sync/` (schema: `schema/sync.schema.json`), and the
recording's `sync` field refers to it.

```json
{
  "version": 1,
  "recording": "r1",
  "anchorType": "bar",
  "updatedAt": "2026-11-14T12:00:00Z",
  "points": [
    { "timeMs": 0,     "bar": 0, "occurrence": 0, "pos": 0,   "source": "manual" },
    { "timeMs": 2150,  "bar": 1, "occurrence": 0, "pos": 0,   "source": "tap" }
  ]
}
```

- `recording` is the id of the recording that the points belong to.
- `anchorType` MUST match the tab format (section 6).
- A point MAY carry `x-` fields. A reader ignores any field of a point that it does not know.
- `points` MUST be sorted by `timeMs`, strictly increasing. Each point has:
  - `timeMs`: milliseconds on the recording's timeline, 0 or more.
  - `source` (optional): `tap`, `manual`, or `auto`. The default is `manual`.
  - `id` (optional).
  - the anchor fields for the anchor type, described below.
- A recording with no sync file, no `syncFrom`, and no `stemOf` has no sync data. That is valid, and the tab and recording
  still travel together.
- **Resolution.** To find the sync points of recording R:
  1. If R has its own `sync` file, use it. Its points are already on R's timeline.
  2. Otherwise, if R has `syncFrom`, find the points of that recording and add R's `syncOffsetMs` (default 0) to each
     `timeMs`.
  3. Otherwise, if R has `stemOf`, find the points of that recording. Add no offset.
  4. Otherwise R has no sync data.

  Each step can lead to another recording, and the offsets along the chain add up. A chain that returns to a recording
  it has already visited is invalid. A reader drops any point whose `timeMs` ends up below 0.
- **`syncOffsetMs`.** Use it when a recording has the same tempo and structure as another but starts earlier or later,
  for example a backing track with a count-in. A positive value means the music starts later than in the recording
  that it shares points with. `syncOffsetMs` MUST NOT appear without `syncFrom`, or together with `sync`.
- **What can be shared.** Sharing assumes the same structure and tempo. A recording with a different arrangement or
  tempo, such as a live version, needs its own `sync` file. A sync file belongs to one recording, because its
  `recording` field must equal that recording's id. Two recordings cannot point `sync` at the same file, so use
  `syncFrom` instead.
- **Exact timing.** A reader that does not know `syncOffsetMs` ignores it and places the cursor too early or too late.
  If exact timing matters, a writer SHOULD give the recording its own `sync` file.
- Before the first point and after the last, a reader holds the first or last position. It MAY extrapolate instead.

### 9.1 Anchor type `bar` (Guitar Pro tabs)

| Field | Type | Meaning |
|---|---|---|
| `bar` | integer ≥ 0 | 0-based index of the bar in the score's master bar list. |
| `occurrence` | integer ≥ 0 | Which pass through that bar, counted in playback order. `0` is the first time the bar is played, and a bar inside a repeat has `occurrence` 1 on its second pass. The default is 0. |
| `pos` | number, 0 to 1 | Position inside the bar, as a fraction of its length. The default is 0. |

Points MUST NOT go backwards in playback order. Between two points, a reader SHOULD interpolate in beats using the
score's tempo map. If the score has no tempo map, the reader SHOULD interpolate linearly in time.

### 9.2 Anchor type `pdf`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `page` | integer ≥ 1 | yes | 1-based page number in the PDF file (when `tab.startPage` and `tab.endPage` are set, `page` is between `startPage` and `endPage` inclusive, not renumbered from 1). |
| `x` | number, 0 to 1 | with `y` | Horizontal position, as a fraction of the page width. |
| `y` | number, 0 to 1 | with `x` | Vertical position, as a fraction of the page height. |

- A point has either both `x` and `y`, or neither. A point with only `page` is a **page anchor**: the playhead is
  somewhere on that page, and a reader turns to the page. A point with `x` and `y` is a **position anchor**.
- `x` and `y` are measured on the page's CropBox (its MediaBox if there is none), after applying the page's `/Rotate`,
  with the origin at the top left. They do not depend on resolution or zoom.
- A position anchor marks where the playhead is, typically at the start of a bar or of a line of music.
- A writer that cannot tell where on the page the playhead is MUST write a page anchor, and MUST NOT make up `x` and `y`.
- A file MAY mix page anchors and position anchors.
- **Order and repeats.** Points are ordered by `timeMs`, not by position. A point may name an earlier place in the tab than
  the point before it. That is a backward jump, and it means the music repeats: a repeat sign, a D.S., a second verse on the
  first page. A backward jump is not an error. Places are compared in reading order: page, then `y`, then `x`. A page
  anchor counts as the top of its page.
- **Between points.** A reader moves from one point to the next as follows. If the next point is a backward jump, or is on
  another page, the reader holds the earlier point until the next one. Otherwise, if both points are position anchors on
  the same page, the reader MAY interpolate. In every other case it holds.
- A writer SHOULD set `tab.pages`. Anchors are valid only for the exact file that `tab.sha256` identifies.

### 9.3 Anchor type `text`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `line` | integer ≥ 0 | yes | 0-based line number. |
| `col` | integer ≥ 0 | no | 0-based column, counted in Unicode code points. |

- Count lines and columns on the decoded text of the tab file. Decode it as UTF-8, remove a leading byte order mark, and
  replace each CRLF and each CR with LF. Columns count Unicode code points, not UTF-16 units or bytes.
- `line` identifies a system. A writer SHOULD use the line of the system's top string row. A reader SHOULD accept any line
  within a block of consecutive non-empty lines and treat it as that block.
- A point without `col` is a **block anchor**: the playhead is somewhere in that block, and the reader shows the block. A
  point with `col` is a **column anchor**. In ASCII tab the string rows of a system line up, so `col` is the playhead
  column for the whole system.
- A writer that knows the column of the bar or beat it is anchoring SHOULD write `col`. A writer that knows only the block
  MUST write a block anchor, and MUST NOT make up a `col`. A writer that has a finer position than a block but cannot
  express it as a column loses that detail. It MAY keep it in `x-` fields on the point, which other readers ignore.
- **Order and repeats.** As for `pdf`, points are ordered by `timeMs`. A point may name an earlier block than the point
  before it, or an earlier column in the same block. That is a backward jump and means the music repeats. Places are
  compared by `line`, then `col`. A block anchor counts as the start of its block.
- **Between points.** If the next point is a backward jump, or is in another block, the reader holds the earlier point
  until the next one. Otherwise, if both points are column anchors in the same block, the reader MAY interpolate. In every
  other case it holds.

## 10. Reader requirements

A reader:

1. MUST open a file with no network access, and MUST NOT make a network request in order to open one.
2. MUST NOT fetch a `url` source, or start a `youtube` source, until the user asks to play that recording.
3. MUST ignore fields, entries, roles, sources and `ids` keys it does not know.
4. MUST reject `version` greater than it supports, with a message saying the file needs a newer reader.
5. MUST treat everything inside the archive as untrusted input (section 12).
6. SHOULD warn when the tab's `sha256` does not match the file.
7. SHOULD NOT fail on a missing optional part. A file with only a tab is a valid file.

Library matching, merging a file into a song as another variation (section 6.2), MusicBrainz lookups, and similar enrichment are application features. They are outside this
specification, and a reader MAY use `song.ids` for them.

## 11. Writer requirements and enrichment

A writer:

1. MUST write `mimetype` first and follow section 3.
2. MUST write the manifest fields marked required.
3. MUST write a valid sync file for each recording that it gives sync points to.
4. MUST store an embedded tab file (`tab.path`) byte for byte (a `txt` tab as UTF-8).
5. SHOULD write `generator`.
6. SHOULD write audio entries Stored, and MUST use ZIP64 where section 3.1 requires it.
7. SHOULD write a file in one pass over its audio, without holding the audio in memory.

### Enrichment

A file is valid if it refers to audio only through `youtube` or `url` sources and holds no audio files. Another tool can
improve such a file:

1. Add `audio/<name>` to the archive.
2. Prepend a `file` source to the same recording (or insert it before the source that the audio was made from). Set
   `derivedFrom` to the `id` of that source. If the audio was trimmed or padded, set `offsetMs` so that the existing sync
   points stay valid.
3. Leave the rest of the manifest and the sync files unchanged. Keep unknown fields and `x-` fields.

This specification defines only the layout of the data. It does not say how to obtain audio. Copying audio from a
service may breach that service's terms and the rights of the people who made the recording. Whether a tool does that is
up to the tool's author and its users (section 14).

## 12. Security

A reader MUST protect against:

- **Path traversal (zip slip).** Reject entries (and `tab.externalPath`) that break the name rules in section 3. When you
  extract an entry to disk, resolve its path inside a directory of your own choosing. When you resolve `tab.externalPath`,
  resolve it inside the directory containing the `.mtab` file. Do not use a path from the archive or manifest as it is.
- **Decompression bombs.** Reject the archive, or stop reading, in any of these cases: an entry inflates to more than 100
  times its stored size, the manifest is over 1 MiB, a sync file is over 8 MiB, or the archive has more than 1000
  entries. A reader MAY use higher limits for `audio/` entries. Inflation is counted on the output, as it is produced (section 3.1).
- **Duplicate and overlapping entries.** Reject archives whose central directory has duplicate names or overlapping data.
- **Active content.** A PDF can contain scripts and links, and an audio file can be malformed. Open both with the same
  precautions as for a file from the internet.
- **Remote content.** `url` and `youtube` sources load third-party content. Load them only when the user asks (section 10),
  and only over `https`.
- **Hash mismatch.** A `sha256` that does not match is a warning, not proof of tampering. A hash is not a signature, and
  it does not show who wrote the file.

## 13. Versioning and extensions

- `version` is the major version. A change that older readers can ignore does not change it. Examples are a new optional
  field, role, source type, or anchor field. A change that older readers cannot ignore does change it.
- Readers ignore what they do not know, so writers can add fields at any time.
- **Extensions.** An application's private fields SHOULD start with `x-`, for example `x-myapp-color`. This specification
  will not define any field that starts with `x-`.
- A reader that rewrites a file SHOULD keep unknown fields and `x-` fields.

## 14. Copyright, patents, names

- **Copyright.** A `.mtab` file can contain a tab and recordings that belong to other people. This specification grants
  no right to them. Writers and distributors are responsible for having the right to include what they include. A file
  can refer to a recording (`youtube`, `url`, `external`) instead of carrying it. A writer SHOULD do that when it does
  not hold the rights to the audio.
- **Patents.** The authors will not assert patent claims against an implementation of this specification as published.
- **Names.** "Multi-Track Tab" and the `.mtab` extension may be used freely to describe files and software that follow
  this specification.
- **Media type.** This specification uses `application/vnd.mtab+zip` provisionally. It is not registered.

## 15. Open questions

These questions are open for a later version. Feedback from implementers would help most.

1. Should interpolation between two position anchors on one page, or two column anchors in one block, be required instead of optional?
2. Should the tab be optional, so that a file with only recordings and sync is valid? Version 1 says no.
3. Should `stem.track` also accept a list, for a stem that mixes two tracks?
4. Is the bar list of a `gp` (Guitar Pro 7 and later) file stable across versions of that format? Track and bar indices
   need a test fixture.
