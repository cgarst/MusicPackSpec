# Changelog

## Version 1

- Added `scoreTracks` to a recording (section 7, "Tracks in a recording"). It maps a score `id` to `omits` or `only`, the
  indexes of the score's tracks that are missing from the audio or the only ones in it, so a reader can mute them for a
  backing track or a solo. Added the defined roles `alternate` and `solo`. A writer no longer has to call an alternate
  version of the song `original` or keep the track list in an `x-` field. Both additions are ignorable by older readers.

- Clarified that two recordings can share a source (section 7, "One source in several recordings"). A writer that has
  several sets of sync points for one video or audio file lists one recording for each set, and a reader keeps them all
  when it merges files. Section 6.2 no longer calls such recordings "the same recording": they are duplicates only when
  their sync points are identical. Added the example `alternate-sync`.

- Added the score format `alphatex` (alphaTex, `.atex`). It uses the `bar` anchor, and section 9.1 defines its bar list: the
  master bars of the source, counted over all staves, with printed bar numbers ignored and repeats not expanded. A score of
  this format MUST be UTF-8, and a reader ignores any `\sync` points inside the file in favour of the sync file.

- Added "Changing a score" to section 11. A writer that replaces or edits a score file in an existing pack must update its
  `sha256` and must either confirm that the sync points still apply or remove them, and the same holds for an alternate.
  A reader or editor that stores sync points outside the file should key them by the score's `sha256`.

- A file can now hold several scores. The manifest field `score` is replaced by the array `scores`, and the first item is the
  primary score. Each score has an `id`, and may have a `label`. Sync is kept per score and recording: a recording's `sync`
  is now a map from a score `id` to a sync file path, and a sync file has a `score` field next to `recording`. Resolution
  through `syncFrom` and `stemOf` runs for one score at a time, so a recording can have its own file for one score and share
  another's points. `syncOffsetMs` may now appear together with `sync`, and applies to the scores that have no entry. An
  `embedded` source can name the score that holds its audio (`score`, default the primary), and stem track links count the
  primary score's tracks. Alternates (section 6.3) stay as the way for a score to reuse another score's sync points, and
  are now listed in the `alternates` array of the score they derive from. Section 6.2, on variations, is replaced by
  "Several scores".

- Replaced `score.tuning` with `score.instruments`. A score can now be for several instruments, each with its own `name`,
  `tuning`, and `capo`, all optional. It is still informational and used only when the score file does not carry the
  information. Tunings are no longer required to be lowest string first, so re-entrant tunings fit.

- Added alternate scores (section 6.3). The manifest's optional `alternates` array lists scores that are derived from the
  main score and keep its structure, such as an easy arrangement or a MusicXML export. The main score's sync points apply
  to them unchanged, so they must have the same anchor type and line up with it. Each alternate has its own `sha256`,
  and `stem.track` links are not applied to alternates.

- Added section 13.1, Extensions. It covers `x-` fields on any object, `x-<name>/` directories in the archive, own values
  in open vocabularies, and the rule that an extension never changes a defined field and is always safe to ignore.

- Removed `defaultRecording`. The first recording in `recordings` is the default, so a writer orders the list.

- Renamed "tab" to "score" throughout. The manifest field `tab` is now `score`, the archive directory `tab/` is now
  `score/`, and the reference code uses `score`, `externalScore` and `scoreEntry`. The one remaining use of "tab" is
  "ASCII tab", the plain-text notation.

- Removed the "Open questions" section and settled each one. Interpolation between anchors stays optional. The tab stays
  required. `stem.track` stays a single index (a stem that mixes tracks has none). Bar and track indices are stable
  because the tab file is stored untouched and pinned by `sha256`.

- Renamed the format from Multi-Track Tab (`.mtab`) to Music Pack (`.mpak`). The manifest marker is now `"format": "mpak"`, the
  media type is `application/vnd.mpak+zip`, the schema ids are `urn:mpak:schema:...`, and the reference code uses `Mpak`
  names (`openMpak`, `MpakError`, `bin/mpak.js`). The name no longer says "tab" because the tab can now be any notation.

- Added tab formats for general notation: `musicxml`, `mxl`, `mscz`, `midi`, and `abc`. `musicxml`, `mxl`, and `mscz` use
  the `bar` anchor (section 9.1 now defines the bar list for each format), `abc` uses `text`, and `midi` uses a new
  `tick` anchor (section 9.4). Track links are ignored for `abc`, as for `pdf` and `txt`.

- Removed the `mimetype` entry. It was borrowed from EPUB and OpenDocument so that byte-sniffing tools could identify the
  file, but nothing used it, and macOS Archive Utility refuses to expand a ZIP whose first entry is `mimetype`. A file is
  now recognised by its extension and by `manifest.json`. Writers no longer write the entry, there is no rule on entry
  order, and a reader ignores a `mimetype` entry in an older file. `isMpakBytes` is removed from the reference code.

- First release: ZIP container, manifest, song metadata (all optional), tab, recordings with several sources,
  stems, and sync anchors for Guitar Pro (`bar`), PDF (`pdf`), and text (`text`) tabs.
- Added `reference/js`: a reference reader, writer, validator, and command-line tool, with container and security tests.
- Added CI (`.github/workflows/ci.yml`).
- A `url` source may use `http` or `https` (it was `https` only). Readers SHOULD warn before loading an `http` source.
- Rewrote the specification text for clarity. No rules changed, except two clarifications: sync points MUST be sorted,
  and a reader MUST NOT depend on entry order.
- Added `syncOffsetMs` on a recording, so a recording can share another's sync points with a time offset (for example a
  backing track with a count-in). Clarified sync resolution, how `stemOf` and an own `sync` interact, and that a sync
  file belongs to one recording.
- Added the `embedded` recording source (audio inside a `gp` tab file), and section 3.1 on large files and streaming
  (ZIP64, reading by range, no hashing of audio to open a file).
- `x` and `y` on a `pdf` point and `col` on a `text` point are now optional (a page anchor and a block anchor), and
  `pdf` and `text` points may jump backward in position to mean a repeat. `bar` points still may not.
- Split `reference/js` into a portable core (`src/core`, no Node dependency, reads through a ByteSource) and a Node shell
  (`src/node`). Ajv is now a development dependency, used only to check the hand-written validator against the schemas.
- Added section 6.1 on multi-song PDFs (`tab.startPage`, `tab.endPage`, and `tab.externalPath` for a shared book PDF outside
  the archive) and section 6.2 on one tab per file and variations.
- Added `song.ids.musicbrainz.releaseGroup`, made octave numbers optional in `tab.tuning`, clarified that enrichment prepends
  a `file` source before the source it was made from, and allowed readers to fall back to a `gp` file's own sync points for
  an `embedded` source when the `.mpak` file has no sync points for that recording.
