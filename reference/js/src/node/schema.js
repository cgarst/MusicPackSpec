// The JSON Schemas in schema/, compiled with Ajv. Used by the tests to check that the portable validator in
// src/core/check.js agrees with the normative schemas. Ajv is a development dependency only.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const SCHEMA_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../schema');
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);
const load = (f) => JSON.parse(fs.readFileSync(path.join(SCHEMA_DIR, f), 'utf8'));
const manifestValidator = ajv.compile(load('manifest.schema.json'));
const syncValidator = ajv.compile(load('sync.schema.json'));
const fmt = (v) => (v.errors || []).map((e) => `${e.instancePath || '<root>'}: ${e.message}`);

export const manifestSchemaErrorsAjv = (m) => { manifestValidator(m); return fmt(manifestValidator); };
export const syncSchemaErrorsAjv = (s) => { syncValidator(s); return fmt(syncValidator); };
