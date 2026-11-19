# Examples

Each folder is an **unpacked** archive: a `manifest.json` and any `sync/` files. The score and audio files that the
manifests name are not included, because they would be copyrighted or binary. The `sha256` values are placeholders of 64
zeros.

To make a real file, add the score (and any audio) at the paths the manifest names, then run `node
reference/js/bin/mpak.js pack <folder> out.mpak`. The tool sets the hashes of the files it finds.

| Folder | Shows |
|---|---|
| `minimal` | The smallest valid file: a score and nothing else. |
| `youtube-only` | A YouTube recording with bar sync, and a repeated bar (`occurrence` 1). |
| `alternate-sync` | The same YouTube video in two recordings, each with its own sync points for the score. |
| `enriched` | The same file after a tool added an audio file (`derivedFrom`). It also carries an extension field (`x-example-app`, section 13.1). |
| `embedded` | A Guitar Pro 7+ score whose own audio track is the recording (`embedded` source), with a YouTube fallback. |
| `stems` | A mix with complete stems mapped to tracks, a backing track that shares the mix's sync with a 2-second offset, a source-less recording, and a third role. |
| `guitar-only` | Guitar-only audio with no mix, and its own sync. |
| `pdf` | A PDF score with page and position sync, and a manual instrument tuning. |
| `text` | A text score with line and column sync. |
| `musicxml` | A MusicXML score with bar sync, and a repeated pass (`occurrence` 1). |
| `multi-score` | Two scores, a Guitar Pro file and a PDF, each with its own sync for one recording, and an easy alternate that reuses the Guitar Pro sync. |
| `origin` | Scores of one file with the same `origin` (four PDFs from one publisher) that a reader can show as one entry, beside a Guitar Pro file and a hand-made chart that have no `origin` and stand alone. |
| `midi` | A MIDI file with tick sync. |
| `alphatex` | An alphaTex score with bar sync. |
| `abc` | An ABC notation score with line sync. |
| `beats` | Beat files: a full mix with a beat grid and sections, a stem and a backing track that inherit it (the backing track through `syncFrom` with an offset), a second backing track that lists the stem it lacks in `without`, and a click track with its own grid. It also has the optional `genre` and `publisher`. |
