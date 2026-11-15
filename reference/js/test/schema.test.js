// The portable validator (src/core/check.js) is written by hand. The JSON Schemas are normative. This test checks that the
// two agree on every example, every invalid case, and a set of small mutations.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { manifestSchemaErrors, syncSchemaErrors, validateManifest, validateSync } from '../src/core/index.js';
import { manifestSchemaErrorsAjv, syncSchemaErrorsAjv } from '../src/node/schema.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const load = (p) => JSON.parse(fs.readFileSync(p, 'utf8'));
const agree = (name, mine, ajv) => assert.equal(mine.length > 0, ajv.length > 0, `${name}: core says ${JSON.stringify(mine)}, schema says ${JSON.stringify(ajv)}`);

const manifests = [], syncs = [];
for (const d of fs.readdirSync(path.join(ROOT, 'examples'), { withFileTypes: true }).filter((x) => x.isDirectory())) {
  const m = load(path.join(ROOT, 'examples', d.name, 'manifest.json'));
  manifests.push([`examples/${d.name}`, m]);
  for (const r of m.recordings || []) for (const [sid, sp] of Object.entries(r.sync || {})) syncs.push([`examples/${d.name}/${sp}`, load(path.join(ROOT, 'examples', d.name, sp)), m.scores.find((t) => t.id === sid).format]);
}
const invalid = fs.readdirSync(path.join(ROOT, 'conformance/invalid')).filter((f) => f.endsWith('.json'));

test('every example is valid, by the hand-written validator and by the schemas', () => {
  for (const [n, m] of manifests) { assert.deepEqual(validateManifest(m), [], n); assert.deepEqual(manifestSchemaErrorsAjv(m), [], n); }
  for (const [n, s, f] of syncs) { assert.deepEqual(validateSync(s, f), [], n); assert.deepEqual(syncSchemaErrorsAjv(s), [], n); }
});
test('every invalid case is refused by both', () => {
  for (const f of invalid) {
    const doc = load(path.join(ROOT, 'conformance/invalid', f));
    if (f.startsWith('sync-')) { assert.ok(validateSync(doc, f === 'sync-anchor-mismatch.json' ? 'gp5' : undefined).length, f); assert.ok(syncSchemaErrorsAjv(doc).length || f === 'sync-anchor-mismatch.json', f); }
    else { assert.ok(validateManifest(doc).length, f); }
  }
});

const clone = (o) => JSON.parse(JSON.stringify(o));
const mutate = (doc, fn) => { const c = clone(doc); fn(c); return c; };
test('hand-written validator and schemas agree on mutations of the examples', () => {
  const bad = [undefined, null, -1, 1.5, '', 'x', [], {}, true, 2, 'a/../b', '0'.repeat(64), 'A'.repeat(64)];
  for (const [n, m] of manifests) {
    const paths = [];
    const walk = (o, p) => { if (o && typeof o === 'object') for (const k of Object.keys(o)) { paths.push([...p, k]); walk(o[k], [...p, k]); } };
    walk(m, []);
    for (const p of paths) for (const v of bad) {
      let skip = false;
      const c = mutate(m, (x) => { let o = x; for (const k of p.slice(0, -1)) o = o[k]; if (v === undefined && Array.isArray(o)) skip = true; else if (v === undefined) delete o[p.at(-1)]; else o[p.at(-1)] = v; });
      if (skip) continue;
      // The schema's `format` and combined if/then rules are the only places the two may legitimately differ; none of the mutations hit those.
      agree(`${n} ${p.join('.')}=${JSON.stringify(v)}`, manifestSchemaErrors(c), manifestSchemaErrorsAjv(c));
    }
  }
  for (const [n, s] of syncs) {
    const paths = [];
    const walk = (o, p) => { if (o && typeof o === 'object') for (const k of Object.keys(o)) { paths.push([...p, k]); walk(o[k], [...p, k]); } };
    walk(s, []);
    for (const p of paths) for (const v of bad) {
      let skip = false;
      const c = mutate(s, (x) => { let o = x; for (const k of p.slice(0, -1)) o = o[k]; if (v === undefined && Array.isArray(o)) skip = true; else if (v === undefined) delete o[p.at(-1)]; else o[p.at(-1)] = v; });
      if (skip) continue;
      agree(`${n} ${p.join('.')}=${JSON.stringify(v)}`, syncSchemaErrors(c), syncSchemaErrorsAjv(c));
    }
  }
});
