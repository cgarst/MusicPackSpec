# Multi-Track Tab (.mtab)

An open file format that packages one song for practice: the **tab**, the **recordings** that go with it (original,
backing track, stems), and the **sync points** that align the tab to each recording.

The file is a ZIP archive of ordinary files, so any language can read and write it. The tab inside is an existing file
(Guitar Pro, PDF, or plain text), stored untouched.

**Version 1.** If you build a tab reader or editor, your feedback
is welcome, especially on the [open questions](SPEC.md#15-open-questions).

## What is in this repository

| Path | Contents |
|---|---|
| [`SPEC.md`](SPEC.md) | The specification |
| [`schema/manifest.schema.json`](schema/manifest.schema.json) | JSON Schema for `manifest.json` |
| [`schema/sync.schema.json`](schema/sync.schema.json) | JSON Schema for sync files |
| [`examples/`](examples) | Unpacked example archives (manifest and sync files) |
| [`conformance/invalid/`](conformance/invalid) | Documents that must be rejected |
| [`tools/check.py`](tools/check.py) | Validates the examples and the invalid cases |
| [`reference/js/`](reference/js) | Reference reader, writer and validator: a portable core, plus a Node shell and command-line tool |

## At a glance

```
song.mtab  (ZIP)
├── manifest.json     song, tab, recordings
├── tab/song.gp5      the tab, byte for byte
├── audio/mix.ogg     optional audio
└── sync/mix.json     optional sync points
```

- Everything about the song is optional. The only required content is a tab.
- A recording can be a file in the archive, a YouTube video, a web address, or only a reference.
- Sync points work for Guitar Pro tabs (by bar), PDF tabs (by page and position), and text tabs (by line and column).
- Stems can be linked to the tab's tracks, so a reader can build a backing mix.

## Check the examples

To validate the examples and the invalid cases, run:

```
python3 -m pip install jsonschema
python3 tools/check.py
```

## Licensing

- The specification text, schemas and examples: [CC BY 4.0](LICENSE-SPEC).
- Code in this repository (`tools/` and `reference/`): [MIT](LICENSE).
- The examples contain no real tabs or recordings. Do not add copyrighted tabs, tab PDFs or audio to this repository.

"Multi-Track Tab" and `.mtab` may be used freely to describe files and software that follow this specification.

## Reference implementation

`reference/js` has two layers.

- **`src/core`** is the portable core: reader, writer and validator. It uses no Node, DOM or `Buffer` API and no package,
  so it runs in Node 22, browsers and webviews. It reads an archive through a **ByteSource**,
  `{ size, read(start, end) -> Promise<Uint8Array> }`, so it opens a file by reading the end of the archive, the
  central directory, the manifest, the tab and the sync files, and no audio. Audio is a byte range
  (`opened.range(path)`) or a stream (`opened.stream(path)`). The writer takes audio as `{ source, start, end }` and returns a
  list of parts to write, so audio is never copied into memory. Both handle ZIP64.
- **`src/node`** adds files on disk (`fileSource`, `openMtabFile`, `writeParts`), a streaming SHA-256 for audio, the
  `mtab` command-line tool, and the Ajv check used by the tests.

In a browser, a source over a `Blob` is `{ size: blob.size, read: async (s, e) => new Uint8Array(await blob.slice(s, e).arrayBuffer()) }`.
To build a `Blob` from the writer's parts, map a source part to `blob.slice(start, end)` on the blob behind that source.

It needs Node 22 or later. The core has no runtime dependencies; Ajv is a development dependency. To run the tests and the tool:

```
cd reference/js && npm ci && npm test
node bin/mtab.js pack <dir> out.mtab      # <dir> is laid out like examples/*; fills in sha256 of files present
node bin/mtab.js validate out.mtab
node bin/mtab.js info out.mtab
node bin/mtab.js unpack out.mtab <emptydir>
```

The tests build real archives from every example, using dummy tab and audio files. They feed the reader hostile archives
(zip slip, duplicate names, decompression bombs, a bad CRC, encryption, overlapping entries), check
that opening a 20 MiB bundle reads under 256 KiB, force ZIP64 on small data and read it back with Python's `zipfile`, check
that `src/core` touches no platform API, and check that the hand-written validator agrees with the JSON Schemas on every
example, invalid case and a set of mutations. `tools/check.py` is a second, independent check of the schemas, written in Python.
