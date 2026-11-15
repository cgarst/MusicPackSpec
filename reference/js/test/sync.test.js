import test from 'node:test';
import assert from 'node:assert/strict';
import { MpakError, openMpak, bytesSource, zipParts, concatParts } from '../src/core/index.js';
import { u8, goodManifest, base } from './helpers.js';

async function syncBundle(recordings, syncs, anchorType = 'text') {
  const m = { ...await goodManifest(), recordings };
  const b = await base();
  const files = [{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]];
  for (const [name, pts] of Object.entries(syncs)) {
    const rec = recordings.find((r) => r.sync?.main === name).id;
    files.push({ name, data: u8(JSON.stringify({ version: 1, recording: rec, score: 'main', anchorType, points: pts.map((t, i) => ({ timeMs: t, line: i, col: 0 })) })) });
  }
  return openMpak(bytesSource(await concatParts((await zipParts(files)).parts)));
}
const times = (s) => s.points.map((p) => p.timeMs);

test('syncFrom with syncOffsetMs shifts the shared points', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: { main: 'sync/a.json' }, sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 2000, sources: [] },
  ], { 'sync/a.json': [0, 1000, 2000] });
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(times(r.sync('a')), [0, 1000, 2000]);
  assert.deepEqual(times(r.sync('b')), [2000, 3000, 4000]);
  assert.equal(r.sync('b').recording, 'b');
});
test('offsets add along a chain, stemOf adds none', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: { main: 'sync/a.json' }, sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 1000, sources: [] },
    { id: 'c', role: 'backing', syncFrom: 'b', syncOffsetMs: 500, sources: [] },
    { id: 's', role: 'stem', stemOf: 'a', sources: [] },
  ], { 'sync/a.json': [0, 1000] });
  assert.deepEqual(times(r.sync('c')), [1500, 2500]);
  assert.deepEqual(times(r.sync('s')), [0, 1000]);
});
test('a negative offset drops points below zero', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: { main: 'sync/a.json' }, sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: -1500, sources: [] },
  ], { 'sync/a.json': [0, 1000, 2000] });
  assert.deepEqual(times(r.sync('b')), [500]);
});
test('own sync wins over stemOf; recordings without sync data resolve to null', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: { main: 'sync/a.json' }, sources: [] },
    { id: 's', role: 'stem', stemOf: 'a', sync: { main: 'sync/s.json' }, sources: [] },
    { id: 'x', role: 'live', sources: [] },
  ], { 'sync/a.json': [0, 1000], 'sync/s.json': [0, 1300] });
  assert.deepEqual(times(r.sync('s')), [0, 1300]);
  assert.equal(r.sync('x'), null);
});
test('rejects syncOffsetMs without syncFrom', async () => {
  const bad = (rec) => assert.rejects(() => syncBundle([{ id: 'a', role: 'original', sources: [] }, rec], {}), MpakError);
  await bad({ id: 'b', role: 'backing', syncOffsetMs: 5, sources: [] });
});
test('a misaligned stem uses syncFrom with an offset', async () => {
  const r = await syncBundle([
    { id: 'a', role: 'original', sync: { main: 'sync/a.json' }, sources: [] },
    { id: 's', role: 'stem', syncFrom: 'a', syncOffsetMs: 250, stem: { instrument: 'guitar', track: 0 }, sources: [] },
  ], { 'sync/a.json': [0, 1000] });
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(times(r.sync('s')), [250, 1250]);
});

// --- embedded source -------------------------------------------------------------------------------------------
test('an embedded source on a gp score is accepted; on another score format it is a warning', async () => {
  const gp = { ...await goodManifest(), scores: [{ id: 'main', path: 'score/a.txt', format: 'gp', sha256: (await goodManifest()).scores[0].sha256 }], recordings: [{ id: 'a', role: 'original', sources: [{ type: 'embedded' }] }] };
  const b = await base();
  const make = async (m) => openMpak(bytesSource(await concatParts((await zipParts([{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]])).parts)));
  assert.deepEqual((await make(gp)).warnings, []);
  const txt = { ...gp, scores: [{ ...gp.scores[0], format: 'txt' }] };
  assert.match((await make(txt)).warnings[0], /embedded source on a txt score/);
});
test('two embedded sources on one recording are refused', async () => {
  const m = { ...await goodManifest(), recordings: [{ id: 'a', role: 'original', sources: [{ type: 'embedded', id: 'e1' }, { type: 'embedded', id: 'e2' }] }] };
  const b = await base();
  const bytes = await concatParts((await zipParts([{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]])).parts);
  await assert.rejects(() => openMpak(bytesSource(bytes)), /more than one embedded/);
});

// --- several scores --------------------------------------------------------------------------------------------
test('sync is resolved per score: a recording can have its own file for one score and inherit for another', async () => {
  const ok = await goodManifest();
  const m = { ...ok, scores: [ok.scores[0], { ...ok.scores[0], id: 'other', path: 'score/b.txt' }], recordings: [
    { id: 'a', role: 'original', sync: { main: 'sync/a-main.json', other: 'sync/a-other.json' }, sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 100, sync: { other: 'sync/b-other.json' }, sources: [] },
  ] };
  const pt = (t) => ({ timeMs: t, line: 0 });
  const f = (name, recording, score, ts) => ({ name, data: u8(JSON.stringify({ version: 1, recording, score, anchorType: 'text', points: ts.map(pt) })) });
  const files = [{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, { name: 'score/a.txt', data: u8('x') }, { name: 'score/b.txt', data: u8('x') },
    f('sync/a-main.json', 'a', 'main', [0, 1000]), f('sync/a-other.json', 'a', 'other', [0, 2000]), f('sync/b-other.json', 'b', 'other', [5, 6])];
  const r = await openMpak(bytesSource(await concatParts((await zipParts(files)).parts)));
  assert.equal(r.warnings.filter((w) => !/score sha256 mismatch: score\/b.txt/.test(w)).length, 0);
  assert.deepEqual(times(r.sync('a')), [0, 1000]);
  assert.deepEqual(times(r.sync('a', 'other')), [0, 2000]);
  assert.deepEqual(times(r.sync('b')), [100, 1100]); // inherits main through syncFrom, with the offset
  assert.deepEqual(times(r.sync('b', 'other')), [5, 6]); // own file for this score
});
test('a sync entry that names an unknown score is refused', async () => {
  const m = { ...await goodManifest(), recordings: [{ id: 'a', role: 'original', sync: { nope: 'sync/a.json' }, sources: [] }] };
  const b = await base();
  const bytes = await concatParts((await zipParts([{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]])).parts);
  await assert.rejects(() => openMpak(bytesSource(bytes)), /unknown score/);
});

async function beatBundle(recordings, beatFiles) {
  const m = { ...await goodManifest(), recordings };
  const b = await base();
  const files = [{ name: 'manifest.json', data: u8(JSON.stringify(m)) }, b[1]];
  for (const [name, doc] of Object.entries(beatFiles)) files.push({ name, data: u8(JSON.stringify(doc)) });
  return openMpak(bytesSource(await concatParts((await zipParts(files)).parts)));
}
const grid = (rec, t, extra = {}) => ({ version: 1, recording: rec, beats: t.map((timeMs) => ({ timeMs })), ...extra });
const btimes = (f) => f.beats.map((x) => x.timeMs);

test('a beat file is read, and shifted through syncFrom and not through stemOf', async () => {
  const r = await beatBundle([
    { id: 'a', role: 'original', beats: 'beats/a.json', sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: 2000, sources: [] },
    { id: 's', role: 'stem', stemOf: 'a', sources: [] },
    { id: 'n', role: 'backing', sources: [] },
  ], { 'beats/a.json': grid('a', [0, 500, 1000], { sections: [{ name: 'Intro', timeMs: 0 }] }) });
  assert.deepEqual(r.warnings, []);
  assert.deepEqual(btimes(r.beats('a')), [0, 500, 1000]);
  assert.deepEqual(btimes(r.beats('b')), [2000, 2500, 3000]);
  assert.equal(r.beats('b').sections[0].timeMs, 2000);
  assert.deepEqual(btimes(r.beats('s')), [0, 500, 1000]);
  assert.equal(r.beats('b').recording, 'b');
  assert.equal(r.beats('n'), null);
});
test('a negative offset drops beats below zero', async () => {
  const r = await beatBundle([
    { id: 'a', role: 'original', beats: 'beats/a.json', sources: [] },
    { id: 'b', role: 'backing', syncFrom: 'a', syncOffsetMs: -600, sources: [] },
  ], { 'beats/a.json': grid('a', [0, 500, 1000]) });
  assert.deepEqual(btimes(r.beats('b')), [400]);
});
test('a bad or mismatched beat file is a warning, and the recording has no beats', async () => {
  const r = await beatBundle([
    { id: 'a', role: 'original', beats: 'beats/a.json', sources: [] },
    { id: 'b', role: 'original', beats: 'beats/b.json', sources: [] },
    { id: 'c', role: 'original', beats: 'beats/missing.json', sources: [] },
  ], { 'beats/a.json': grid('a', [500, 500]), 'beats/b.json': grid('other', [0]) });
  assert.equal(r.warnings.length, 3);
  assert.equal(r.beats('a'), null);
  assert.equal(r.beats('b'), null);
});
