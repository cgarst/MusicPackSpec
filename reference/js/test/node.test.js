import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { sha256, isMtabBytes, bytesSource, openMtab } from '../src/core/index.js';
import { packDirToBytes, packDir, writeParts, openMtabFile, audioHashWarnings, readDir } from '../src/node/index.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const examples = fs.readdirSync(path.join(ROOT, 'examples'), { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name);

// Examples ship without tab/audio files (copyright). Stage a copy with dummy files.
function stage(name) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mtab-'));
  fs.cpSync(path.join(ROOT, 'examples', name), dir, { recursive: true });
  const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json'), 'utf8'));
  const put = (p, data) => { fs.mkdirSync(path.dirname(path.join(dir, p)), { recursive: true }); fs.writeFileSync(path.join(dir, p), data); };
  put(m.tab.path || m.tab.externalPath, `dummy tab for ${name}\n`.repeat(50));
  for (const r of m.recordings || []) for (const s of r.sources) if (s.type === 'file') put(s.path, Buffer.alloc(4096, 7));
  return dir;
}

for (const name of examples) {
  test(`example ${name} packs and reads back`, async () => {
    const bytes = await packDirToBytes(stage(name));
    assert.ok(isMtabBytes(bytes));
    const r = await openMtab(bytesSource(bytes));
    assert.deepEqual(r.warnings, []);
    assert.equal(r.manifest.format, 'mtab');
    assert.equal(await sha256(r.tab), r.manifest.tab.sha256);
    for (const rec of r.manifest.recordings || []) if (rec.sync || rec.syncFrom || rec.stemOf) assert.ok(r.sync(rec.id), `sync resolves for ${rec.id}`);
  });
}

test('output is reproducible', async () => {
  const dir = stage('enriched');
  assert.deepEqual(await packDirToBytes(dir), await packDirToBytes(dir));
});

test('audio entries are stored, tab is deflated', async () => {
  const bytes = Buffer.from(await packDirToBytes(stage('enriched')));
  const r = await openMtab(bytesSource(bytes));
  assert.equal(r.entries[0], 'mimetype');
  const method = (n) => bytes.readUInt16LE(bytes.indexOf(Buffer.from(n)) - 30 + 8);
  assert.equal(method('audio/r1.ogg'), 0);
  assert.equal(method('tab/example.gp5'), 8);
});

test('a bundle written to disk opens by range, and the audio hash is checked by streaming', async () => {
  const dir = stage('enriched');
  const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'mtab-out-')), 'out.mtab');
  await writeParts(f, (await packDir(dir)).parts);
  const r = await openMtabFile(f);
  try {
    assert.deepEqual(r.warnings, []);
    assert.deepEqual(await audioHashWarnings(r), []);
  } finally { await r.close(); }
  // flip one audio byte: opening still works (audio is not read to open), and streaming the entry fails its CRC-32
  const bytes = fs.readFileSync(f);
  bytes[bytes.indexOf(Buffer.alloc(64, 7))] = 8;
  fs.writeFileSync(f, bytes);
  const r2 = await openMtabFile(f);
  try {
    assert.deepEqual(r2.warnings, []);
    await assert.rejects(() => audioHashWarnings(r2), /crc mismatch/);
  } finally { await r2.close(); }
});

test('readDir replaces placeholder hashes', async () => {
  const { manifest } = await readDir(stage('minimal'));
  assert.notEqual(manifest.tab.sha256, '0'.repeat(64));
});

test('externalPath is hashed on packDir, omitted from archive, and resolved on openMtabFile', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mtab-ext-'));
  const pdf = Buffer.from('%PDF-1.4 multi-song book\n');
  fs.mkdirSync(path.join(dir, 'books'), { recursive: true });
  fs.writeFileSync(path.join(dir, 'books/book.pdf'), pdf);
  fs.writeFileSync(path.join(dir, 'manifest.json'), JSON.stringify({
    format: 'mtab',
    version: 1,
    tab: { externalPath: 'books/book.pdf', format: 'pdf', sha256: '0'.repeat(64), pages: 20, startPage: 4, endPage: 7 },
  }));
  const { manifest, files } = await readDir(dir);
  assert.equal(manifest.tab.sha256, await sha256(pdf));
  assert.equal(files.has('books/book.pdf'), false);
  const out = path.join(dir, 'song.mtab');
  await writeParts(out, (await packDir(dir)).parts);
  const r = await openMtabFile(out);
  try {
    assert.deepEqual(r.warnings, []);
    assert.equal(r.entries.includes('books/book.pdf'), false);
    assert.deepEqual(Buffer.from(r.tab), pdf);
  } finally { await r.close(); }
  // When external PDF is missing on disk, openMtabFile warns instead of throwing
  fs.unlinkSync(path.join(dir, 'books/book.pdf'));
  const rMissing = await openMtabFile(out);
  try {
    assert.equal(rMissing.tab, null);
    assert.match(rMissing.warnings[0], /missing external tab file/);
  } finally { await rMissing.close(); }
});
