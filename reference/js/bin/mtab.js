#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { openMtabFile, audioHashWarnings, packDir, writeParts, MtabError } from '../src/node/index.js';

const [cmd, a, b] = process.argv.slice(2);
const usage = () => { console.error('usage: mtab pack <dir> <out.mtab> | info <file.mtab> | validate <file.mtab> | unpack <file.mtab> <emptydir>'); process.exit(2); };
try {
  if (cmd === 'pack' && a && b) { await writeParts(b, (await packDir(a)).parts); console.log(`wrote ${b}`); }
  else if ((cmd === 'info' || cmd === 'validate') && a) {
    const r = await openMtabFile(a);
    try {
      const warnings = [...r.warnings, ...(cmd === 'validate' ? await audioHashWarnings(r) : [])];
      for (const w of warnings) console.error(`warning: ${w}`);
      if (cmd === 'info') console.log(JSON.stringify({ manifest: r.manifest, entries: r.entries }, null, 2));
      else console.log(`ok (${r.entries.length} entries, ${warnings.length} warnings)`);
    } finally { await r.close(); }
  } else if (cmd === 'unpack' && a && b) {
    const r = await openMtabFile(a);
    try {
      if (fs.existsSync(b) && fs.readdirSync(b).length) throw new MtabError('target directory is not empty');
      const root = path.resolve(b);
      for (const name of r.entries) {
        const dest = path.resolve(root, name);
        if (!dest.startsWith(root + path.sep)) throw new MtabError(`refusing ${name}`);
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        const out = fs.createWriteStream(dest);
        for await (const chunk of r.stream(name)) if (!out.write(chunk)) await new Promise((ok) => out.once('drain', ok));
        await new Promise((ok, no) => out.end((e) => (e ? no(e) : ok())));
      }
    } finally { await r.close(); }
  } else usage();
} catch (e) {
  if (e instanceof MtabError) { console.error(`error: ${e.message}`); process.exit(1); }
  throw e;
}
