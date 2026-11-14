import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { MIMETYPE, MtabError, buildMtab, concatParts, openMtab, bytesSource, sha256, zipParts, isMtabBytes, entryRange, validateManifest } from '../src/core/index.js';
import { u8, goodManifest, base, build, open } from './helpers.js';

const rejects = async (files, re, opts) => {
  const bytes = await build(files, opts ?? { unchecked: true });
  await assert.rejects(() => open(bytes), (e) => e instanceof MtabError && re.test(e.message));
};

// --- container rules -------------------------------------------------------------------------------------------
test('baseline hand-built archive is accepted', async () => assert.deepEqual((await open(await build(await base()))).warnings, []));
test('rejects mimetype not first', async () => { const b = await base(); await rejects([b[1], b[0], b[2]], /first entry/); });
test('rejects wrong mimetype', async () => { const b = await base(); await rejects([{ name: 'mimetype', data: u8('application/zip'), store: true }, ...b.slice(1)], /mimetype/); });
test('rejects compressed mimetype', async () => { const b = await base(); await rejects([{ ...b[0], store: false, data: u8(MIMETYPE.repeat(20)) }, ...b.slice(1)], /first entry|mimetype/); });
test('rejects missing manifest', async () => { const b = await base(); await rejects([b[0], b[2]], /manifest/); });
test('rejects zip slip entry', async () => rejects([...await base(), { name: '../evil', data: u8('x') }], /bad entry name/));
test('rejects absolute and backslash names', async () => {
  await rejects([...await base(), { name: '/abs', data: u8('x') }], /bad entry name/);
  await rejects([...await base(), { name: 'a\\b', data: u8('x') }], /bad entry name/);
});
test('rejects duplicate names, also by case', async () => {
  await rejects([...await base(), { name: 'tab/a.txt', data: u8('y') }], /duplicate/);
  await rejects([...await base(), { name: 'TAB/A.TXT', data: u8('y') }], /duplicate/);
});
test('rejects version 2', async () => { const b = await base(); await rejects([b[0], { name: 'manifest.json', data: u8(JSON.stringify({ ...await goodManifest(), version: 2 })) }, b[2]], /version/); });
test('rejects manifest with BOM', async () => {
  const b = await base();
  const data = new Uint8Array([0xef, 0xbb, 0xbf, ...u8(JSON.stringify(await goodManifest()))]);
  await rejects([b[0], { name: 'manifest.json', data }, b[2]], /byte order mark/);
});
test('rejects oversized manifest', async () => { const b = await base(); await rejects([b[0], { name: 'manifest.json', data: u8(JSON.stringify({ ...await goodManifest(), pad: 'x'.repeat(1 << 21) })) }, b[2]], /too large/); });
test('rejects decompression bomb, counting output as it is produced', async () => {
  const b = await base();
  const o = await open(await build([...b, { name: 'sync/bomb.json', data: new Uint8Array(5 << 20) }]));
  assert.deepEqual(o.warnings, []); // not referenced by the manifest, so never inflated
  await assert.rejects(() => o.file('sync/bomb.json', 8 << 20), /ratio|limit/);
  const reader = o.stream('sync/bomb.json').getReader();
  await assert.rejects(async () => { for (;;) { const { done } = await reader.read(); if (done) return; } }, /ratio|limit/);
});
test('rejects a lying central directory size (inflates past the stated size)', async () => {
  const b = await base();
  const bytes = Buffer.from(await build([...b, { name: 'x/a', data: new Uint8Array(1 << 20) }]));
  const cen = bytes.lastIndexOf(Buffer.from([0x50, 0x4b, 1, 2]), bytes.indexOf(Buffer.from('x/a'), bytes.length - 200));
  bytes.writeUInt32LE(10, cen + 24); // claim 10 bytes
  const o = await open(bytes);
  await assert.rejects(() => o.file('x/a'), MtabError);
});
test('rejects too many entries', async () => {
  const f = [...await base()];
  for (let i = 0; i < 1001; i++) f.push({ name: `x/${i}`, data: new Uint8Array(0) });
  await rejects(f, /too many/);
});
test('rejects corrupted data (crc)', async () => {
  const bytes = await build(await base());
  bytes[Buffer.from(bytes).indexOf(Buffer.from('tab/a.txt')) + 9] ^= 0xff;
  await assert.rejects(() => open(bytes), MtabError);
});
test('rejects encrypted flag', async () => {
  const bytes = Buffer.from(await build(await base()));
  bytes[bytes.indexOf(Buffer.from([0x50, 0x4b, 1, 2])) + 8] |= 1;
  await assert.rejects(() => open(bytes), /encrypted/);
});
test('rejects overlapping entries', async () => {
  const bytes = Buffer.from(await build(await base()));
  const cens = []; for (let i = 0; i < bytes.length - 4; i++) if (bytes.readUInt32LE(i) === 0x02014b50) cens.push(i);
  bytes.writeUInt32LE(bytes.readUInt32LE(cens[1] + 42), cens[2] + 42);
  await assert.rejects(() => open(bytes), MtabError);
});
test('rejects bytes that are not a zip', async () => {
  await assert.rejects(() => open(new Uint8Array(100)), MtabError);
  await assert.rejects(() => open(new Uint8Array(5)), MtabError);
});
test('hash mismatch is a warning, not an error', async () => {
  const b = await base();
  const m = { ...await goodManifest(), tab: { ...(await goodManifest()).tab, sha256: '0'.repeat(64) } };
  const o = await open(await build([b[0], { name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[2]]));
  assert.match(o.warnings[0], /sha256 mismatch/);
});
test('unknown extra entries and x- fields are ignored', async () => {
  const b = await base();
  const m = { ...await goodManifest(), 'x-app': { a: 1 } };
  const o = await open(await build([b[0], { name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[2], { name: 'extra/foo.bin', data: u8('q') }]));
  assert.deepEqual(o.warnings, []);
});
test('writer refuses an invalid manifest', async () => assert.rejects(() => buildMtab({ format: 'mtab', version: 1 }, {}), MtabError));
test('isMtabBytes recognises the start of a bundle', async () => {
  assert.ok(isMtabBytes(await build(await base())));
  assert.ok(!isMtabBytes(u8('PK\x03\x04 not a bundle, but long enough to be checked, really')));
  assert.ok(!isMtabBytes(new Uint8Array(10)));
});
test('stored entries survive a round trip with real content', async () => {
  const big = new Uint8Array(zlib.deflateRawSync(Buffer.alloc(1000, 1)));
  const o = await open(await build([...await base(), { name: 'audio/a.bin', data: big, store: true }]));
  assert.deepEqual(await o.file('audio/a.bin'), big);
});

// --- reading by range ------------------------------------------------------------------------------------------
test('opening a bundle with 20 MiB of audio reads a small fraction of it, and no audio', async () => {
  const audio = new Uint8Array(20 << 20).fill(9);
  const m = { ...await goodManifest(), recordings: [{ id: 'r1', role: 'original', sources: [{ type: 'file', path: 'audio/big.bin' }] }] };
  const b = await base();
  const bytes = await build([b[0], { name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[2], { name: 'audio/big.bin', data: audio, store: true }]);
  let read = 0;
  const src = { size: bytes.length, read: async (s, e) => { read += Math.min(e, bytes.length) - s; return bytes.subarray(s, e); } };
  const o = await openMtab(src);
  assert.deepEqual(o.warnings, []);
  assert.ok(read < 256 << 10, `read ${read} bytes`);
  const r = o.range('audio/big.bin');
  assert.equal(r.end - r.start, audio.length);
  assert.deepEqual(bytes.subarray(r.start, r.start + 8), audio.subarray(0, 8)); // playable straight from the archive
  const chunks = []; for await (const c of o.stream('audio/big.bin')) chunks.push(c.length);
  assert.equal(chunks.reduce((a, c) => a + c, 0), audio.length);
  assert.ok(Math.max(...chunks) <= 1 << 20, 'streamed in chunks');
});
test('entryRange is null for a compressed entry', async () => {
  const o = await open(await build([...await base(), { name: 'sync/a.json', data: u8('{}'.repeat(500)) }]));
  assert.equal(o.range('sync/a.json'), null);
});
test('writing takes audio as a source range and does not copy it', async () => {
  const audio = new Uint8Array(3 << 20).fill(5);
  const src = bytesSource(audio);
  const b = await base();
  const plan = await zipParts([...b, { name: 'audio/a.bin', data: { source: src } }]);
  assert.ok(plan.parts.some((p) => !(p instanceof Uint8Array) && p.source === src && p.end - p.start === audio.length));
  const o = await open(await concatParts(plan.parts));
  assert.deepEqual(await o.file('audio/a.bin'), audio);
});

// --- ZIP64 -----------------------------------------------------------------------------------------------------
test('zip64 records are written and read back (forced with a low threshold)', async () => {
  const files = [...await base(), { name: 'audio/a.bin', data: new Uint8Array(500).fill(3), store: true }, { name: 'sync/z.json', data: u8('{}') }];
  const bytes = await build(files, { zip64Threshold: 100 });
  const o = await open(bytes);
  assert.deepEqual(await o.file('audio/a.bin'), new Uint8Array(500).fill(3));
  assert.equal((await o.file('sync/z.json')).length, 2);
  const py = spawnSync('python3', ['-c', 'import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; print(len(z.namelist()))', (() => { const f = path.join(os.tmpdir(), `z64-${process.pid}.zip`); fs.writeFileSync(f, bytes); return f; })()]);
  if (py.error) return; // no python3 here
  assert.equal(py.status, 0, py.stderr?.toString());
  assert.equal(py.stdout.toString().trim(), String(files.length));
});
test('the first entry cannot be zip64', async () => { const b = await base(); await assert.rejects(() => zipParts(b, { zip64Threshold: 10 }), /first entry/); });
// --- portability -----------------------------------------------------------------------------------------------
test('src/core uses no Node, DOM or Buffer API', () => {
  const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '../src/core');
  for (const f of fs.readdirSync(dir)) {
    const text = fs.readFileSync(path.join(dir, f), 'utf8').replace(/\/\/.*$/gm, '');
    assert.ok(!/node:|\bBuffer\b|\brequire\(|\bprocess\b|\bwindow\b|\bdocument\b|\bfs\./.test(text), `${f} touches a platform API`);
    assert.ok(!/^import .* from '(?!\.\/)/m.test(text), `${f} imports a package`);
  }
});
test('sha256 matches Node for a known value', async () => assert.equal(await sha256(u8('abc')), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'));

// --- tuning, multi-song pdf, externalPath ----------------------------------------------------------------------
test('tuning accepts pitch names with or without octaves', () => {
  const baseM = { format: 'mtab', version: 1, tab: { path: 'tab/a.txt', format: 'txt', sha256: '0'.repeat(64) } };
  assert.deepEqual(validateManifest({ ...baseM, tab: { ...baseM.tab, tuning: ['D', 'A', 'D', 'G', 'B', 'E'] } }), []);
  assert.deepEqual(validateManifest({ ...baseM, tab: { ...baseM.tab, tuning: ['E2', 'A2', 'D3', 'G3', 'B3', 'E4'] } }), []);
  assert.ok(validateManifest({ ...baseM, tab: { ...baseM.tab, tuning: ['H', 'A'] } }).length);
});

test('multi-song PDF startPage/endPage bounds are validated', () => {
  const pdfTab = { path: 'tab/book.pdf', format: 'pdf', sha256: '0'.repeat(64), pages: 10 };
  assert.deepEqual(validateManifest({ format: 'mtab', version: 1, tab: { ...pdfTab, startPage: 3, endPage: 7 } }), []);
  assert.deepEqual(validateManifest({ format: 'mtab', version: 1, tab: { ...pdfTab, startPage: 5, endPage: 5 } }), []);
  assert.ok(validateManifest({ format: 'mtab', version: 1, tab: { ...pdfTab, startPage: 6, endPage: 5 } }).length);
  assert.ok(validateManifest({ format: 'mtab', version: 1, tab: { ...pdfTab, startPage: 11 } }).length);
  assert.ok(validateManifest({ format: 'mtab', version: 1, tab: { ...pdfTab, endPage: 11 } }).length);
});

test('externalPath opens without embedding the PDF and checks sha256 when provided', async () => {
  const pdfBytes = u8('%PDF-1.4 shared book');
  const m = { format: 'mtab', version: 1, tab: { externalPath: 'books/jazz.pdf', format: 'pdf', sha256: await sha256(pdfBytes), startPage: 2, endPage: 4 } };
  const parts = await buildMtab(m, {});
  const archive = await concatParts(parts.parts);
  const withoutExternal = await openMtab(bytesSource(archive));
  assert.equal(withoutExternal.tab, null);
  assert.deepEqual(withoutExternal.warnings, []);
  const withExternal = await openMtab(bytesSource(archive), { externalTab: (rel) => (rel === 'books/jazz.pdf' ? pdfBytes : null) });
  assert.deepEqual(withExternal.tab, pdfBytes);
  assert.deepEqual(withExternal.warnings, []);
  const mismatch = await openMtab(bytesSource(archive), { externalTab: u8('%PDF-1.4 wrong') });
  assert.match(mismatch.warnings[0], /sha256 mismatch/);
});
