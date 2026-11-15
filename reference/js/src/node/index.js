// Node shell around the portable core: files on disk, a streaming SHA-256, and the schema check used by the tests.
// Everything that needs `node:` lives here. src/core never imports it.
import fs from 'node:fs';
import crypto from 'node:crypto';
import path from 'node:path';
import { openMpak, buildMpak, verifyAudioHash, concatParts, scoreEntry, sha256, MpakError } from '../core/index.js';

export * from '../core/index.js';

/** A ByteSource over a file. Call `close()` when done. */
export async function fileSource(p) {
  const fh = await fs.promises.open(p, 'r');
  const { size } = await fh.stat();
  return {
    size,
    read: async (start, end) => {
      const n = Math.max(0, Math.min(end, size) - start);
      const buf = new Uint8Array(n);
      let got = 0;
      while (got < n) {
        const { bytesRead } = await fh.read(buf, got, n - got, start + got);
        if (!bytesRead) break;
        got += bytesRead;
      }
      return buf.subarray(0, got);
    },
    close: () => fh.close(),
  };
}

/** Opens a .mpak file on disk. Returns the opened bundle with an added `close()`. */
export async function openMpakFile(p, opts = {}) {
  const source = await fileSource(p);
  const root = path.dirname(path.resolve(p));
  const externalScore = opts.externalScore ?? (async (rel, warnings) => {
    const dest = path.resolve(root, rel);
    if (!dest.startsWith(root + path.sep)) throw new MpakError(`refusing external score path ${rel}`);
    if (!fs.existsSync(dest)) { warnings.push(`missing external score file ${rel}`); return null; }
    return new Uint8Array(await fs.promises.readFile(dest));
  });
  try {
    const opened = await openMpak(source, { ...opts, externalScore });
    return { ...opened, close: () => source.close() };
  } catch (e) { await source.close(); throw e; }
}

export const nodeHasher = () => { const h = crypto.createHash('sha256'); return { update: (u8) => h.update(u8), digest: () => h.digest('hex') }; };

/** Checks the sha256 of every audio file source, streaming each one. Returns the list of mismatch messages. */
export async function audioHashWarnings(opened) {
  const out = [];
  for (const r of opened.manifest.recordings || []) for (const s of r.sources || []) {
    if (s.type === 'file' && s.sha256 && opened.entries.includes(s.path) && await verifyAudioHash(opened, s, nodeHasher) === false) out.push(`audio sha256 mismatch: ${s.path}`);
  }
  return out;
}

/** Writes parts to a file, copying source ranges in chunks. */
export async function writeParts(p, parts) {
  const fh = await fs.promises.open(p, 'w');
  try {
    for (const part of parts) {
      if (part instanceof Uint8Array) { await fh.write(part); continue; }
      for (let at = part.start; at < part.end; at += 1 << 20) await fh.write(await part.source.read(at, Math.min(part.end, at + (1 << 20))));
    }
  } finally { await fh.close(); }
}

/** Reads an unpacked directory (laid out like examples/*) into { manifest, files }. Placeholder hashes are replaced when the file exists. */
export async function readDir(dir, { fixHashes = true } = {}) {
  const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  const files = new Map();
  const walk = (d) => { for (const n of fs.readdirSync(d, { withFileTypes: true })) {
    const full = path.join(d, n.name);
    if (n.isDirectory()) walk(full);
    else if (n.name !== 'manifest.json') files.set(path.relative(dir, full).split(path.sep).join('/'), new Uint8Array(fs.readFileSync(full)));
  } };
  walk(dir);
  if (fixHashes) {
    const tp = manifest.score.path || manifest.score.externalPath;
    if (tp && files.has(tp)) manifest.score.sha256 = await sha256(files.get(tp));
    for (const r of manifest.recordings || []) for (const s of r.sources || [])
      if (s.type === 'file' && files.has(s.path)) s.sha256 = await sha256(files.get(s.path));
  }
  if (manifest.score.externalPath) files.delete(manifest.score.externalPath);
  return { manifest, files };
}

/** Packs an unpacked directory into a bundle's parts. */
export async function packDir(dir, opts) {
  const { manifest, files } = await readDir(dir, opts);
  return buildMpak(manifest, files);
}

export const packDirToBytes = async (dir, opts) => concatParts((await packDir(dir, opts)).parts);

export { scoreEntry };
