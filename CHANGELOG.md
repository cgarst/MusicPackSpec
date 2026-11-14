# Changelog

## Version 1

- Removed the `mimetype` entry. It was borrowed from EPUB and OpenDocument so that byte-sniffing tools could identify the
  file, but nothing used it, and macOS Archive Utility refuses to expand a ZIP whose first entry is `mimetype`. A file is
  now recognised by its extension and by `manifest.json`. Writers no longer write the entry, there is no rule on entry
  order, and a reader ignores a `mimetype` entry in an older file. `isMtabBytes` is removed from the reference code.

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
  an `embedded` source when the `.mtab` file has no sync points for that recording.
