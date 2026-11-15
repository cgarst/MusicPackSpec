import { zipParts, concatParts, openMpak, bytesSource } from '../src/core/index.js';

const enc = new TextEncoder();
export const u8 = (s) => enc.encode(s);
export const goodManifest = async () => ({ format: 'mpak', version: 1, tab: { path: 'tab/a.txt', format: 'txt', sha256: await sha(u8('x')) } });
import { sha256 as sha } from '../src/core/index.js';

export const base = async () => [
  { name: 'manifest.json', data: u8(JSON.stringify(await goodManifest())) },
  { name: 'tab/a.txt', data: u8('x') },
];
export const build = async (files, opts) => concatParts((await zipParts(files, opts)).parts);
export const open = (bytes, limits) => openMpak(bytesSource(bytes), limits && { limits });
