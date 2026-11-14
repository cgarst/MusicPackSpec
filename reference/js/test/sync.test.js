import test from 'node:test';
import assert from 'node:assert/strict';
import { MtabError, openMtab, bytesSource, zipParts, concatParts } from '../src/core/index.js';
import { u8, goodManifest, base } from './helpers.js';

async function syncBundle(recordings, syncs, anchorType = 'text') {
  const m = { ...await goodManifest(), recordings };
  const b = await base();
  const files = [{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]];
  for (const [name, pts] of Object.entries(syncs)) {
    const rec = recordings.find((r) => r.sync === name).id;
    files.push({ name, data: u8(JSON.stringify({ version: 1, recording: rec, anchorType, points: pts.map((t, i) => ({ timeMs: t, line: i, col: 0 })) })) });
  }
  return openMtab(bytesSource(await concatParts((await zipParts(files)).parts)));
}
const times = (s) => s.points.map((p) => p.timeMs);

test('syncFrom with syncOffsetMs shifts the shared points', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: 'sync/a.json', sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 2000, sources: [] },
  ], { 'sync/a.json': [0, 1000, 2000] });
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(times(r.sync('a')), [0, 1000, 2000]);
  assert.deepEqual(times(r.sync('b')), [2000, 3000, 4000]);
  assert.equal(r.sync('b').recording, 'b');
});
test('offsets add along a chain, stemOf adds none', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: 'sync/a.json', sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 1000, sources: [] },
    { id: 'c', role: 'backing', syncFrom: 'b', syncOffsetMs: 500, sources: [] },
    { id: 's', role: 'stem', stemOf: 'a', sources: [] },
  ], { 'sync/a.json': [0, 1000] });
  assert.deepEqual(times(r.sync('c')), [1500, 2500]);
  assert.deepEqual(times(r.sync('s')), [0, 1000]);
});
test('a negative offset drops points below zero', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: 'sync/a.json', sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: -1500, sources: [] },
  ], { 'sync/a.json': [0, 1000, 2000] });
  assert.deepEqual(times(r.sync('b')), [500]);
});
test('own sync wins over stemOf; recordings without sync data resolve to null', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: 'sync/a.json', sources: [] },
    { id: 's', role: 'stem', stemOf: 'a', sync: 'sync/s.json', sources: [] },
    { id: 'x', role: 'live', sources: [] },
  ], { 'sync/a.json': [0, 1000], 'sync/s.json': [0, 1300] });
  assert.deepEqual(times(r.sync('s')), [0, 1300]);
  assert.equal(r.sync('x'), null);
});
test('rejects syncOffsetMs without syncFrom or with an own sync file', async () => {
  const bad = (rec) => assert.rejects(() => syncBundle([{ id: 'a', role: 'original', sources: [] }, rec], {}), MtabError);
  await bad({ id: 'b', role: 'backing', syncOffsetMs: 5, sources: [] });
  await bad({ id: 'b', role: 'backing', syncFrom: 'a', sync: 'sync/b.json', syncOffsetMs: 5, sources: [] });
});
test('a misaligned stem uses syncFrom with an offset', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: 'sync/a.json', sources: [] },
    { id: 's', role: 'stem', syncFrom: 'a', syncOffsetMs: 250, stem: { instrument: 'guitar', track: 0 }, sources: [] },
  ], { 'sync/a.json': [0, 1000] });
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(times(r.sync('s')), [250, 1250]);
});

// --- embedded source -------------------------------------------------------------------------------------------
test('an embedded source on a gp tab is accepted; on another tab format it is a warning', async () => {
  const gp = { ...await goodManifest(), tab: { path: 'tab/a.txt', format: 'gp', sha256: (await goodManifest()).tab.sha256 }, recordings: [{ id: 'a', role: 'original', sources: [{ type: 'embedded' }] }] };
  const b = await base();
  const make = async (m) => openMtab(bytesSource(await concatParts((await zipParts([{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]])).parts)));
  assert.deepEqual((await make(gp)).warnings, []);
  const txt = { ...gp, tab: { ...gp.tab, format: 'txt' } };
  assert.match((await make(txt)).warnings[0], /embedded source on a txt tab/);
});
test('two embedded sources on one recording are refused', async () => {
  const m = { ...await goodManifest(), recordings: [{ id: 'a', role: 'original', sources: [{ type: 'embedded', id: 'e1' }, { type: 'embedded', id: 'e2' }] }] };
  const b = await base();
  const bytes = await concatParts((await zipParts([{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]])).parts);
  await assert.rejects(() => openMtab(bytesSource(bytes)), /more than one embedded/);
});
