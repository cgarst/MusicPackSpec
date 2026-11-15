# Music Pack (.mpak)

An open file format that packages one song: one or more **scores**, the **recordings** that go with it (original,
backing track, stems), and the **sync points** that align each score to each recording.

The file is a ZIP archive of ordinary files, so any language can read and write it. The score inside is an existing file
(Guitar Pro, MusicXML, MuseScore, MIDI, ABC, PDF, or plain text), stored untouched.

**Version 1.** Feedback is welcome from anyone who builds a score reader or editor.

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
song.mpak  (ZIP)
├── manifest.json    song, scores, recordings
├── score/song.gp5   the score, byte for byte
├── audio/mix.ogg    optional audio
└── sync/mix.json    optional sync points
```

- The song metadata, recordings, and sync points are all optional. The only required content is a score.
- A recording can be a file in the archive, a YouTube video, a web address, or only a reference.
- Sync points work with these scores:
  - Guitar Pro, MusicXML, and MuseScore: by bar.
  - MIDI: by tick.
  - PDF: by page and position.
  - Text and ABC: by line and column.
- A stem can be linked to a track in the score, so a reader can build a backing mix.

## Check the examples

To validate the examples and the invalid cases, run these commands:

```
python3 -m pip install jsonschema
python3 tools/check.py
```

## Licensing

- The specification text, schemas and examples: [CC BY 4.0](LICENSE-SPEC).
- Code in this repository (`tools/` and `reference/`): [MIT](LICENSE).
- The examples contain no real scores or recordings. Do not add copyrighted scores, score PDFs or audio to this repository.

"Music Pack" and `.mpak` may be used freely to describe files and software that follow this specification.

## Reference implementation

`reference/js` has two layers:

- **`src/core`** is the portable core: reader, writer and validator. It uses no Node, DOM, or `Buffer` API and no package,
  so it runs in Node 22, browsers, and webviews. It reads an archive through a **ByteSource**,
  `{ size, read(start, end) -> Promise<Uint8Array> }`. To open a file, it reads the end of the archive, the
  central directory, the manifest, the score, and the sync files, but no audio. You get audio as a byte range
  (`opened.range(path)`) or a stream (`opened.stream(path)`). The writer takes audio as `{ source, start, end }` and returns a
  list of parts to write, so it never copies audio into memory. Both handle ZIP64.
- **`src/node`** adds files on disk (`fileSource`, `openMpakFile`, `writeParts`), a streaming SHA-256 for audio, the
  `mpak` command-line tool, and the Ajv check that the tests use.

In a browser, create a source over a `Blob` like this:
`{ size: blob.size, read: async (s, e) => new Uint8Array(await blob.slice(s, e).arrayBuffer()) }`.
To build a `Blob` from the writer's parts, map each source part to `blob.slice(start, end)` on the blob behind that source.

The reference implementation needs Node 22 or later. The core has no runtime dependencies, and Ajv is a development dependency. To run the tests and the tool, use these commands:

```
cd reference/js && npm ci && npm test
node bin/mpak.js pack <dir> out.mpak      # <dir> is laid out like examples/*; fills in sha256 of files present
node bin/mpak.js validate out.mpak
node bin/mpak.js info out.mpak
node bin/mpak.js unpack out.mpak <emptydir>
```

The tests:

- Build real archives from every example, using dummy score and audio files.
- Feed the reader hostile archives: zip slip, duplicate names, decompression bombs, a bad CRC, encryption, and
  overlapping entries.
- Check that opening a 20 MiB bundle reads under 256 KiB.
- Force ZIP64 on small data and read it back with Python's `zipfile`.
- Check that `src/core` touches no platform API.
- Check that the hand-written validator agrees with the JSON Schemas on every example, every invalid case, and a set of
  mutations.

`tools/check.py` is a second, independent check of the schemas, written in Python.
