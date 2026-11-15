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
| `midi` | A MIDI file with tick sync. |
| `abc` | An ABC notation score with line sync. |
