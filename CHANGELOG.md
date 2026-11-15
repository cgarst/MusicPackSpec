# Changelog

## Version 1

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
