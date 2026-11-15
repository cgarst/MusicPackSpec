# Music Pack (.mpak) Specification

**Version 1.** Changes within version 1 only add optional things. A change that breaks existing files is a new version, and the manifest `version` field says which one a file uses.

A Music Pack file (extension `.mpak`) packages one song for practice. It holds the score, the recordings that go with
it (original, backing track, stems), and the sync points that align the score to each recording. The file is a ZIP archive
of ordinary files, so any language can read and write it.

The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are used as defined in RFC 2119.

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

- One file carries everything needed to practice a song: score, recordings, sync, and tuning.
- Any score reader can adopt all of it or only the part it needs (see Profiles).
- A file written by a simple script (a title and a score) is as valid as one written by a full application.
- Another tool can improve a file later, for example by adding audio files, without breaking it.

Non-goals:

- It does not define a new notation format. The score inside is an existing file, stored untouched.
- It does not define playback engines, user interfaces, or library matching.
- It does not put several scores in one file. A song with several scores is several files (section 6.1).
- It does not require any network service. A reader MUST be able to open a file without network access.

## 2. Profiles

A profile is a subset of this specification that a reader can implement on its own. A reader states which profiles it
supports. A writer SHOULD target the smallest profile that holds its data.

| Profile | Covers | Sections |
|---|---|---|
| **Core** | Container, manifest, song metadata, the score | 3 to 6 |
| **Playback** | Core, plus recordings and sync points | 7, 9 |
| **Stems** | Playback, plus stems | 8 |

A Core reader ignores `recordings` and sync files. A Playback reader plays stem recordings as ordinary recordings.

## 3. Container

A `.mpak` file is a ZIP archive. It uses the ISO/IEC 21320 subset of ZIP, plus ZIP64 where needed. The archive has this
layout:

```
manifest.json     the manifest (section 4)
score/<name>        the score file, byte for byte as supplied (omitted when score.externalPath is used; section 6)
                  and the files of any alternate scores (section 6.3)
audio/<name>      optional audio files
sync/<name>.json  optional sync files (section 9)
x-<name>/...      optional extension files of one application (section 13.1)
```

Rules:

1. The archive has no `mimetype` entry, and a writer MUST NOT write one. A reader recognises a file by its `manifest.json`
   (`format` is `mpak`), together with the `.mpak` extension and the media type `application/vnd.mpak+zip`. An entry named
   `mimetype` in a file from an earlier writer is an entry the manifest does not name (rule 7), so a reader ignores it.
2. `manifest.json` MUST be present. It MUST be UTF-8 JSON with no byte order mark, and at most 1 MiB.
3. Entry names MUST be UTF-8 and use `/` as the separator. A name MUST be relative and MUST NOT contain a `..` segment,
   an empty segment, a backslash, or a control character. Names MUST be unique, also when compared case-insensitively.
4. The compression method MUST be Stored or Deflate. Encryption MUST NOT be used.
5. Audio entries SHOULD be Stored. Audio is already compressed, and a Stored entry lets a reader seek without inflating.
6. A reader MUST NOT depend on entry order. The manifest MUST NOT hold offsets or
   checksums of the archive itself. (Hashes of file contents are fine.) This lets a tool rewrite the archive.
7. An entry that the manifest does not name is allowed, and readers MUST ignore it. A writer that rewrites a file SHOULD
   keep such entries.

### 3.1 Large files and streaming

A file can hold hours of audio, so this specification sets no size limit of its own.

1. A writer MUST use ZIP64 where the ZIP format requires it: an entry or offset of 4 GiB or more, or 65535 or more
   entries. A reader MUST read ZIP64.
2. A reader MUST be able to open a file without reading its audio. Opening needs only the end of the archive, the
   central directory, the manifest, the score and the sync files. The reader SHOULD read these by
   random access, not load the whole archive into memory.
3. A reader MUST take sizes, offsets and checksums from the central directory, and MUST ignore any different value in a
   local header. A writer MAY use data descriptors.
4. A Stored audio entry is a contiguous byte range of the archive. A reader MAY play or copy it from that range without
   inflating or copying it. It MAY skip the CRC-32 check for such an entry, because checking it means reading all of it.
5. A reader that inflates an entry MUST count the output as it goes and stop at the limits in section 12. It MUST NOT
   trust the sizes in the archive for that.
6. A reader MUST NOT hash audio in order to open a file. It MAY check a `sha256` of an audio source later, on demand or in
   the background.
7. The score, the manifest and the sync files are read whole. A reader MAY refuse a score larger than 256 MiB.

## 4. Manifest

`manifest.json` is a JSON object. Its JSON Schema is `schema/manifest.schema.json`.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `format` | `"mpak"` | yes | Format marker. |
| `version` | integer, `1` | yes | Spec major version. A reader MUST reject a higher value and say so. |
| `createdAt` | string, date-time | no | When the file was created. |
| `generator` | `{ name, version? }` | no | The software that wrote the file. |
| `song` | object | no | Section 5. May be empty or absent. |
| `score` | object | yes | Section 6. |
| `alternates` | array | no | Alternate scores derived from `score`, which share its sync points. Section 6.3. |
| `recordings` | array | no | Section 7. |

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
exists: metadata inside the score file, the score's file name, the name of the `.mpak` file.

## 6. Score

`score` describes the one score in the file.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `path` | string | unless `externalPath` | Archive path of the score file, under `score/`. |
| `externalPath` | string | unless `path` | Relative path to a shared PDF file outside the archive (`pdf` only). |
| `format` | enum | yes | `gp3`, `gp4`, `gp5`, `gp` (Guitar Pro 7 and later), `gpx`, `musicxml` (uncompressed MusicXML), `mxl` (compressed MusicXML), `mscz` (MuseScore), `midi` (Standard MIDI File), `abc` (ABC notation), `pdf`, `txt`. |
| `sha256` | string | yes | Lowercase hex SHA-256 of the score file's bytes. |
| `name` | string | no | The original file name, for display. |
| `pages` | integer | no | Page count of the PDF file, for `pdf`. |
| `startPage` | integer | no | 1-based first page of this song inside a multi-song PDF (`pdf` only). |
| `endPage` | integer | no | 1-based last page of this song inside a multi-song PDF (`pdf` only, `>= startPage`, `<= pages`). |
| `tuning` | string array | no | Tuning, lowest string first, as pitch names with or without octave numbers, for example `["E2","A2","D3","G3","B3","E4"]` or `["D","A","D","G","B","E"]`. |

- The score is required. A file with only recordings and sync is not valid, because sync points need a score to anchor to.
- `score` MUST have either `path` or `externalPath`, and MUST NOT have both. `externalPath` is allowed only when `format`
  is `pdf`.
- Bar and track indices count what the stored score file lists, and the file is stored untouched and pinned by `sha256`,
  so a later version of the score's format cannot change what an index means. A reader reads the file with the rules of
  the format version that wrote it (`gp`, `mscz`).
- A writer MUST store an embedded score file (`path`) exactly as supplied and MUST NOT convert or re-encode it. The one
  exception is a `txt` or `abc` score, which MUST be UTF-8. A writer converts any other encoding and records the hash of the
  converted file.
- `sha256` identifies the score file that the sync anchors and stem track links were written against (for an external PDF,
  the whole PDF file). If a reader finds a different hash, it SHOULD tell the user that sync points may be wrong. It
  MUST NOT silently apply track links (section 8).
- `tuning` is for scores that do not carry their own, mainly `pdf` and `txt`. For formats that carry a tuning, the tuning in the file
  wins. A writer SHOULD omit `tuning` for those formats or make it agree with the file.
- The format decides the anchor type that sync uses (section 9): `gp3`, `gp4`, `gp5`, `gp`, `gpx`, `musicxml`, `mxl`,
  and `mscz` use `bar`; `midi` uses `tick`; `pdf` uses `pdf`; `txt` and `abc` use `text`.
- The score can be for any instrument. `tuning` and the Guitar Pro formats are a guitar-oriented part of the list,
  not a limit on what a file can hold.

### 6.1 Multi-song PDFs (`startPage`, `endPage`, and `externalPath`)

A single PDF, such as a songbook, can hold several songs. Each song is its own `.mpak` file, and `startPage` and
`endPage` give its 1-based inclusive page range inside that PDF. Both fields are allowed only when `format` is `pdf`.
When both are present, `endPage` MUST be greater than or equal to `startPage`. When `pages` is also present, both
`startPage` and `endPage` MUST be at most `pages`. When only `startPage` is set, the song runs from `startPage` to the
end of the PDF; when only `endPage` is set, it runs from page 1 to `endPage`.

The PDF itself may either be stored inside the archive (`path`, under `score/`) or left outside the archive and referenced
by `externalPath`, so that several `.mpak` files for songs from the same book can share one copy of the PDF instead of
duplicating it in every archive:

- `externalPath` follows the same safe relative path rules as archive entry names (section 3): UTF-8, `/` separated, no
  leading `/`, no backslash, no `.`, `..`, or empty segment, and no control characters.
- When a reader opens a `.mpak` file from a directory on disk, it resolves `externalPath` inside that directory (and MUST
  reject any path that escapes it; section 12). A reader with its own library MAY also locate the PDF by `score.sha256`, or
  ask the user for the file when it is missing.
- `score.sha256` is still required when `externalPath` is used, and is the SHA-256 of the whole PDF file.

### 6.2 One score per file, and variations

A file holds exactly one main score. A song with several independent scores, for example a Guitar Pro file and a PDF of
the same song, or two arrangements, is several `.mpak` files. (A simplified or re-instrumented version of the main
score that keeps its structure is an alternate, not a variation; section 6.3.) Each one is a **variation** of the song. This specification does not define a
container for a set of variations.

A reader MAY import a file as another variation of a song that it already has. How it finds that song (by `song.ids`, by
`title` and `artist`, or by asking the user) is outside this specification (section 10). When it does:

1. The file's score, recordings and sync stay together as one variation. Sync points belong to the score that `score.sha256`
   identifies (and to that score's alternates, section 6.3) and MUST NOT be applied to another variation, even of the same song, because their anchors are written
   against different score bytes and may have different anchor types.
2. The reader MUST NOT overwrite or remove the sync points, recordings or score of a variation it already has, unless the
   user asks it to. A file whose `score.sha256` matches an existing variation is the same variation: the reader SHOULD NOT
   add a duplicate, and MAY offer to add the file's recordings and sync points to it.
3. Variations MAY share a recording. Two recordings with the same `youtube` `videoId`, or the same audio `sha256`, are the
   same recording, and a reader MAY store it once. Sync is still kept per variation.
4. A file holds one variation, so an export of a song holds the data of one main score and its alternates. The recordings, sync points and score of the
   song's other variations are not in it. A tool that exports several variations writes one file for each, and SHOULD put
   the same `song` metadata in each, so that a reader can match them.

### 6.3 Alternate scores

An **alternate** is another score that is derived from the main score and keeps its structure, so that the main score's
sync points are valid for it unchanged. Examples: an easy or simplified arrangement, a version transposed or with
different fingering, a bass-only or vocals-only reduction, a MusicXML export of a Guitar Pro score, a re-engraved
copy. Alternates are listed in the manifest's `alternates` array. Each item has all the fields of `score` (section 6),
plus:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Identifier, unique among the alternates (same character rules as recording ids). |
| `label` | string | no | Name for display, such as `"Easy"` or `"Bass reduction"`. |

```json
"score": { "path": "score/song.gp", "format": "gp", "sha256": "..." },
"alternates": [
  { "id": "easy", "label": "Easy", "path": "score/song-easy.gp", "format": "gp", "sha256": "..." },
  { "id": "xml",  "label": "MusicXML export", "path": "score/song.musicxml", "format": "musicxml", "sha256": "..." }
]
```

- **Same sync data.** The file has one set of sync points per recording, written against the main `score` (section 9). A
  reader applies those points to an alternate as they are. The alternate MUST therefore have the same anchor type as the
  main score (section 9), and MUST line up with it: bar `n` (with its `occurrence` and `pos`) is the same music in both,
  and has the same repeat and jump structure; for `tick` anchors, the same tick resolution and tempo map; for `text`
  anchors, the same lines. A writer MUST NOT list a score as an alternate when its structure differs (a different bar
  count, a re-ordered form, a different layout). That score is a variation (section 6.2), in its own file with its
  own sync. A `pdf` alternate is rarely derivable this way: it is valid only when its pages and coordinates match the
  main PDF's.
- **The main score stays the reference.** `score` is the default and is the score that sync, `sha256` checks, and stem
  track links are written against. A reader shows the main score unless the user picks an alternate. Order in
  `alternates` is a display order only.
- **Files.** Each alternate has `path` or `externalPath` under the same rules as the main score (section 6, 6.1), and its
  own `sha256`. A writer stores an embedded alternate byte for byte. An alternate's `sha256` is checked on its own: a
  mismatch means a reader SHOULD warn and MAY refuse to show that alternate, and does not affect the main score.
- **Track links.** `stem.track` counts the main score's tracks (section 8). A reader MUST NOT apply a `stem.track` index to
  an alternate. It MAY find the track by `stem.trackName`, when exactly one track in the alternate has that name.
  Otherwise it mutes nothing.
- **Tuning and metadata** are per alternate. An alternate MAY have a different `tuning` (for example drop D), even though
  its bar structure matches.
- A reader that does not know `alternates` ignores it (section 10), and shows only the main score.


## 7. Recordings

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
| `url` | `url` (required, `http` or `https`), `mime` | Audio at a web address. |
| `embedded` | none | Audio carried inside the score file itself, for example the audio track of a Guitar Pro 7 or later (`gp`) file. |
| `external` | none | A recording that exists but has no playable source here. `sha256` and `durationMs` help identify it. |

An `embedded` source has no `path`: the bytes are in the score file that `score.path` names, and the reader extracts them
with its own code for that score format. Rules:

- It is defined for the score format `gp`. For any other score format a reader skips it, and a writer MUST NOT write it.
- It is valid only for the exact score file that `score.sha256` identifies. If the hash does not match, a reader MUST skip
  the source.
- `offsetMs` places the embedded audio on the recording's timeline, like any other source. When the recording has sync
  points (section 9), they apply instead of the score's own sync points. When the recording has no sync points in the
  `.mpak` file, a reader MAY fall back to the sync points stored inside the `gp` file.
- A tool MAY extract the audio into `audio/<name>` and prepend a `file` source to the same recording (or place it before
  the `embedded` source), with `derivedFrom` set to the embedded source's `id` (section 11). The `embedded` source stays,
  so the file still round trips.
- A recording can have only one `embedded` source, because a score file has one audio track.

Other types are allowed. A source of any type MAY appear on any recording, including a stem.

### Default recording

The first recording in `recordings` is the default. A reader uses it first, and a writer puts the recording it wants
used first at the start of the list. There is no separate field for this.

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
| `stem.track` | 0-based index into the score's track list (formats that list tracks only). |
| `stem.trackName` | Optional. The name of that track, used as a check. |
| `stemsComplete` | On the recording that the stems were split from: `true` when the stems add up to the whole mix. |

- **Guitar-only audio.** If the stem was split from a mix, give it `stemOf`. If there is no mix, leave out `stemOf` and
  give the stem its own sync file.
- **One track per stem.** `stem.track` is a single index. A stem that mixes two tracks has no `track`, and a reader
  mutes nothing for it. A writer that wants per-track muting for those tracks splits them into separate stems.
- **A split of each guitar track.** Use several stems with `instrument: "guitar"`, each with a different `track`.
- **Track links.** `stem.track` is the index of the track in the order that the score file lists its tracks. If
  `stem.trackName` is present and the track at that index has a different name, the reader looks for exactly one track
  with that name and uses it. If it finds none or several, it ignores the link and mutes nothing, because a wrong mute is
  worse than no mute. A reader MUST also ignore track links when the score's `sha256` does not match the score file, and
  when the score format is `pdf`, `txt`, or `abc`.
- **Building a backing mix.** If the mix has `stemsComplete: true`, a reader MAY play all its stems except the ones
  linked to the track being practiced. A separate `backing` recording is then optional.
- **A stem that is not aligned with its parent.** Do not use `stemOf` for it. Give it `role: "stem"` and `stem`, and set
  `syncFrom` to the mix with a `syncOffsetMs` (section 9).
- **Stems with no mix.** Suppose the file has stems but no recording that they were split from, and the first
  recording is one of those stems. Then the default is all of those stems played together.
- The stems of one split share one timeline and one duration.

## 9. Sync

A sync file aligns the score to one recording. It is a JSON file under `sync/` (schema: `schema/sync.schema.json`), and the
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
- `anchorType` MUST match the score format (section 6). The points are written against the main score and also apply to
  its alternates (section 6.3).
- A point MAY carry `x-` fields. A reader ignores any field of a point that it does not know.
- `points` MUST be sorted by `timeMs`, strictly increasing. Each point has:
  - `timeMs`: milliseconds on the recording's timeline, 0 or more.
  - `source` (optional): `tap`, `manual`, or `auto`. The default is `manual`.
  - `id` (optional).
  - the anchor fields for the anchor type, described below.
- A recording with no sync file, no `syncFrom`, and no `stemOf` has no sync data. That is valid, and the score and recording
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

### 9.1 Anchor type `bar` (Guitar Pro, MusicXML, and MuseScore scores)

| Field | Type | Meaning |
|---|---|---|
| `bar` | integer ≥ 0 | 0-based index of the bar in the score's master bar list: the bars in the order that the file lists them, with repeats not expanded. |
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

### 9.2 Anchor type `pdf`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `page` | integer ≥ 1 | yes | 1-based page number in the PDF file (when `score.startPage` and `score.endPage` are set, `page` is between `startPage` and `endPage` inclusive, not renumbered from 1). |
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
- A writer SHOULD set `score.pages`. Anchors are valid only for the exact file that `score.sha256` identifies.

### 9.3 Anchor type `text`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `line` | integer ≥ 0 | yes | 0-based line number. |
| `col` | integer ≥ 0 | no | 0-based column, counted in Unicode code points. |

- Count lines and columns on the decoded text of the score file (`txt` or `abc`). Decode it as UTF-8, remove a leading byte order mark, and
  replace each CRLF and each CR with LF. Columns count Unicode code points, not UTF-16 units or bytes.
- `line` identifies a system (for `abc`, a line of music in the source). A writer SHOULD use the line of the system's top string row. A reader SHOULD accept any line
  within a block of consecutive non-empty lines and treat it as that block.
- A point without `col` is a **block anchor**: the playhead is somewhere in that block, and the reader shows the block. A
  point with `col` is a **column anchor**. In ASCII tab the string rows of a system line up, so `col` is the playhead
  column for the whole system. In `abc`, `col` is a position in the source line, which is only approximate for the music.
- A writer that knows the column of the bar or beat it is anchoring SHOULD write `col`. A writer that knows only the block
  MUST write a block anchor, and MUST NOT make up a `col`. A writer that has a finer position than a block but cannot
  express it as a column loses that detail. It MAY keep it in `x-` fields on the point, which other readers ignore.
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
6. SHOULD warn when the score's `sha256` (or an alternate's) does not match the file.
7. SHOULD NOT fail on a missing optional part. A file with only a score is a valid file.

Library matching, merging a file into a song as another variation (section 6.2), MusicBrainz lookups, and similar enrichment are application features. They are outside this
specification, and a reader MAY use `song.ids` for them.

## 11. Writer requirements and enrichment

A writer:

1. MUST follow section 3.
2. MUST write the manifest fields marked required.
3. MUST write a valid sync file for each recording that it gives sync points to.
4. MUST store an embedded score file (`score.path`) byte for byte (a `txt` or `abc` score as UTF-8).
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

- **Path traversal (zip slip).** Reject entries (and `score.externalPath`) that break the name rules in section 3. When you
  extract an entry to disk, resolve its path inside a directory of your own choosing. When you resolve `score.externalPath`,
  resolve it inside the directory containing the `.mpak` file. Do not use a path from the archive or manifest as it is.
- **Decompression bombs.** Reject the archive, or stop reading, in any of these cases: an entry inflates to more than 100
  times its stored size, the manifest is over 1 MiB, a sync file is over 8 MiB, or the archive has more than 1000
  entries. A reader MAY use higher limits for `audio/` entries. Inflation is counted on the output, as it is produced (section 3.1).
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
  field, role, source type, or anchor field. A change that older readers cannot ignore does change it.
- Readers ignore what they do not know, so writers can add fields at any time.
- A reader that rewrites a file SHOULD keep unknown fields and `x-` fields, and unknown archive entries.

### 13.1 Extensions

A file MAY carry data that this specification does not define. Extensions let an application keep its own data in the
file without a new version and without breaking other readers.

- **Extension fields.** Any JSON object in `manifest.json` or in a sync file MAY have extra fields. This covers the
  manifest itself and `song`, `score`, recordings, sources, `stem`, sync files and sync points. The name of an extension
  field MUST start with `x-` followed by a short name for the application or vendor, for example `x-myapp-color`. This
  specification will not define any field that starts with `x-`. A field without the `x-` prefix that this
  specification does not define is reserved for later versions, and a writer SHOULD NOT use one.
- **Extension files.** An application MAY add archive entries under a directory named `x-<name>/`, where `<name>` is the
  same short name, for example `x-myapp/waveform.bin`. The entry names follow section 3, and rule 7 of section 3 applies:
  readers ignore them. The manifest MAY point to them from an extension field.
- **Open vocabularies.** Where this specification says a vocabulary is open (`role`, `stem.instrument`, source `type`), an
  application MAY use values of its own. A reader that does not know a value follows the rule given for that field. Use
  a name that is unlikely to clash, such as `x-myapp-loop`. The closed lists (`score.format` and `anchorType`) are
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
- **Media type.** This specification uses `application/vnd.mpak+zip` provisionally. It is not registered.
