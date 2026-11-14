# Examples

Each folder is an **unpacked** archive: a `manifest.json` and any `sync/` files. The tab and audio files that the
manifests name are not included, because they would be copyrighted or binary. The `sha256` values are placeholders of 64
zeros.

To make a real file, add the tab (and any audio) at the paths the manifest names, then run `node
reference/js/bin/mtab.js pack <folder> out.mtab`. The tool sets the hashes of the files it finds and writes `mimetype`
first, stored.

| Folder | Shows |
|---|---|
| `minimal` | The smallest valid file: a tab and nothing else. |
| `youtube-only` | A YouTube recording with bar sync, and a repeated bar (`occurrence` 1). |
| `enriched` | The same file after a tool added an audio file (`derivedFrom`). |
| `embedded` | A Guitar Pro 7+ tab whose own audio track is the recording (`embedded` source), with a YouTube fallback. |
| `stems` | A mix with complete stems mapped to tracks, a backing track that shares the mix's sync with a 2-second offset, a source-less recording, and a third role. |
| `guitar-only` | Guitar-only audio with no mix, and its own sync. |
| `pdf` | A PDF tab with page and position sync, and a manual tuning. |
| `text` | A text tab with line and column sync. |
