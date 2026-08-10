/**
 * C0 contract round-trip: the frozen studio.contract/v0.1 fixtures stored in fixtures/
 * validate against the JSON Schema definitions in schemas/ (the same instances the
 * Python side validates with `jsonschema`). This proves the fixture set is shared
 * across Python and TypeScript with one source of truth.
 *
 * These tests are fixture-only; none of the instances are production fallbacks.
 */
import { describe, it, expect } from 'vitest';
import Ajv2020 from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgDir = path.join(here, '..', '..');
const schemasDir = path.join(pkgDir, 'schemas');
const fixturesDir = path.join(pkgDir, 'fixtures');

const loadJson = (file: string) => JSON.parse(readFileSync(file, 'utf8'));

// Fixture metadata keys carried in instance files for traceability. They are not part of
// the frozen payload and are stripped before schema validation.
const METADATA_KEYS = ['fixture_id', 'purpose', 'expected_consumer_behavior'];
const stripMetadata = (instance: Record<string, unknown>): Record<string, unknown> => {
  const copy = { ...instance };
  for (const key of METADATA_KEYS) delete copy[key];
  return copy;
};

const manifest = loadJson(path.join(fixturesDir, 'manifest.json')) as {
  contract_version: string;
  fixtures: Array<{ id: string; file: string; schema: string; kind: string }>;
};

const schemaFiles = readdirSync(schemasDir).filter((f) => f.endsWith('.schema.json'));

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

// Canonical URI under which every schema is registered for cross-file $ref resolution.
const CANONICAL_NS = 'https://windagent.io/schemas/';

// Rewrite relative file refs (e.g. "studio.episode-state.schema.json#/$defs/state")
// into absolute canonical URIs so both Ajv and the Python referencing.Registry
// resolve them deterministically regardless of each schema's $id.
const canonicalizeRefs = (node: unknown): unknown => {
  if (Array.isArray(node)) return node.map(canonicalizeRefs);
  if (node && typeof node === 'object') {
    const out: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(node)) {
      if (key === '$ref' && typeof value === 'string' && value.includes('.schema.json')) {
        out[key] = value.replace(/^([^#]+\.schema\.json)/, `${CANONICAL_NS}$1`);
      } else {
        out[key] = canonicalizeRefs(value);
      }
    }
    return out;
  }
  return node;
};

const schemas: Record<string, unknown> = {};
for (const file of schemaFiles) {
  const schema = loadJson(path.join(schemasDir, file));
  schemas[file] = schema;
  // $id is stripped so the registration key is the single identity Ajv uses.
  const canonical = canonicalizeRefs({ ...(schema as object), $id: undefined });
  ajv.addSchema(canonical as object, CANONICAL_NS + file);
}

// Vocabulary fixtures are not single instances; their values must be subsets of the
// frozen schema enums (schema is the authority, never the fixture).
const vocabularyChecks: Record<string, (instance: any, schema: any) => void> = {
  'episode-state.progression': (inst, schema) => {
    const enumValues = schema.$defs.state.enum as string[];
    for (const value of [...inst.states, ...inst.terminal_states]) {
      expect(enumValues, `${value} must be a frozen episode state`).toContain(value);
    }
    expect(inst.states[inst.states.length - 1]).toBe('READY_FOR_PRODUCTION');
  },
  'run-status.valid': (inst, schema) => {
    expect(schema.enum).toContain(inst.status);
    for (const value of inst.all_statuses) {
      expect(schema.enum as string[]).toContain(value);
    }
  },
  'approval-mode.all': (inst, schema) => {
    const modes = schema.properties.mode.enum as string[];
    const checkpoints = schema.properties.checkpoint.enum as string[];
    for (const mode of inst.modes) expect(modes).toContain(mode);
    for (const checkpoint of inst.checkpoints) expect(checkpoints).toContain(checkpoint);
    const validate = ajv.getSchema(CANONICAL_NS + 'studio.approval-mode.schema.json');
    for (const policy of inst.policy) {
      expect(validate!(policy), `policy entry must validate: ${JSON.stringify(policy)}`).toBe(true);
    }
  },
  'idempotency-headers.valid': (inst, schema) => {
    const validate = ajv.getSchema(CANONICAL_NS + 'studio.idempotency-headers.schema.json');
    expect(validate!(inst.headers)).toBe(true);
  },
};

describe('studio.contract/v0.1 fixture round-trip (shared with Python)', () => {
  it('manifest is frozen at the contract version', () => {
    expect(manifest.contract_version).toBe('studio.contract/v0.1');
  });

  it('every manifest fixture file exists and resolves a known schema', () => {
    for (const entry of manifest.fixtures) {
      expect(() => loadJson(path.join(fixturesDir, entry.file))).not.toThrow();
      expect(schemas[entry.schema]).toBeDefined();
    }
  });

  it('valid-kind fixtures validate against their JSON Schema', () => {
    for (const entry of manifest.fixtures.filter((f) => f.kind === 'valid')) {
      const raw = loadJson(path.join(fixturesDir, entry.file)) as Record<string, unknown>;
      const instance = stripMetadata(raw);
      const validate = ajv.getSchema(CANONICAL_NS + entry.schema);
      expect(validate, `validator must exist for ${entry.schema}`).toBeTruthy();
      const ok = validate!(instance);
      expect(ok, `${entry.id} should validate: ${JSON.stringify((validate as any).errors)}`).toBe(true);
    }
  });

  it('vocabulary-kind fixtures stay within the frozen schema enums', () => {
    for (const entry of manifest.fixtures.filter((f) => f.kind === 'vocabulary')) {
      const check = vocabularyChecks[entry.id];
      expect(check, `vocabulary check must exist for ${entry.id}`).toBeDefined();
      const raw = loadJson(path.join(fixturesDir, entry.file));
      check(stripMetadata(raw), schemas[entry.schema]);
    }
  });

  it('negative-malformed fixtures fail validation with a stable error', () => {
    for (const entry of manifest.fixtures.filter((f) => f.kind === 'negative-malformed')) {
      const raw = loadJson(path.join(fixturesDir, entry.file)) as Record<string, unknown>;
      const instance = stripMetadata(raw);
      const validate = ajv.getSchema(CANONICAL_NS + entry.schema);
      expect(validate).toBeTruthy();
      expect(validate!(instance)).toBe(false);
      expect((validate as any).errors).toBeTruthy();
    }
  });

  it('negative-unsupported-version fixtures validate at envelope level (consumer must detect discriminator)', () => {
    for (const entry of manifest.fixtures.filter((f) => f.kind === 'negative-unsupported-version')) {
      const raw = loadJson(path.join(fixturesDir, entry.file)) as Record<string, unknown>;
      const instance = stripMetadata(raw);
      const validate = ajv.getSchema(CANONICAL_NS + entry.schema);
      expect(validate, 'envelope must remain forward-compatible').toBeTruthy();
      expect(validate!(instance)).toBe(true);
      expect(instance.artifact_type).toBeDefined();
      expect(instance.schema_version).toBeDefined();
    }
  });

  it('cross-file $ref schemas resolve against canonical URIs', () => {
    const episode = schemas['studio.episode.schema.json'] as { properties?: Record<string, unknown> };
    const stateRef = (episode.properties?.state as { $ref?: string })?.$ref;
    expect(stateRef).toContain('studio.episode-state.schema.json');
    const refFile = stateRef?.split('#')[0];
    expect(refFile).toBeDefined();
    expect(schemas[refFile as string]).toBeDefined();
    const validate = ajv.compile(ajv.getSchema(CANONICAL_NS + 'studio.episode.schema.json')?.schema ?? {});
    expect(typeof validate).toBe('function');
  });

  it('frozen vocabulary matches the cross-plan contract values', () => {
    const states = JSON.stringify(schemas['studio.episode-state.schema.json']);
    expect(states).toContain('READY_FOR_PRODUCTION');
    expect(states).toContain('STORY_BIBLE_REVIEW');

    const runStatus = JSON.stringify(schemas['studio.run-status.schema.json']);
    expect(runStatus).toContain('WAITING_FOR_APPROVAL');

    const approval = JSON.stringify(schemas['studio.approval-mode.schema.json']);
    expect(approval).toContain('HUMAN_REQUIRED');
    expect(approval).toContain('QUALITY_GATE_ONLY');

    const errors = JSON.stringify(schemas['studio.error-payload.schema.json']);
    expect(errors).toContain('IDEMPOTENCY_MISMATCH');
    expect(errors).toContain('CAPABILITY_UNAVAILABLE');
    expect(errors).toContain('STALE_REVISION');
    expect(errors).toContain('PROVIDER_UNAVAILABLE');
  });

  it('schemas align with the frozen bootstrap fixture set (single source of truth)', () => {
    const bootstrapDir = path.join(pkgDir, '..', '..', '..', 'docs', 'plans', 'studio_roadmap_01', 'fixtures', 'studio_contract_v0.1');

    const errors = loadJson(path.join(bootstrapDir, 'errors.json')) as { errors: Array<{ code: string; http_status: number }> };
    const errorCodes = (schemas['studio.error-payload.schema.json'] as { properties: { code: { enum: string[] }; status: { enum: number[] } } }).properties;
    expect(new Set(errorCodes.code.enum)).toEqual(new Set(errors.errors.map((e) => e.code)));
    expect(new Set(errorCodes.status.enum)).toEqual(new Set(errors.errors.map((e) => e.http_status)));

    const envelope = loadJson(path.join(bootstrapDir, 'artifact_envelope.json')) as { artifact_types: string[] };
    const knownTypes = (schemas['studio.artifact-envelope.schema.json'] as { properties: { artifact_type: { description: string } } }).properties.artifact_type.description;
    for (const artifactType of envelope.artifact_types) {
      expect(knownTypes).toContain(artifactType);
    }

    const lifecycle = loadJson(path.join(bootstrapDir, 'episode_lifecycle.json')) as {
      states: string[];
      approval_modes: string[];
      approval_checkpoints: string[];
    };
    const statesSchema = schemas['studio.episode-state.schema.json'] as { $defs: { state: { enum: string[] } } };
    expect(new Set(statesSchema.$defs.state.enum)).toEqual(new Set(lifecycle.states));
    const approval = schemas['studio.approval-mode.schema.json'] as { properties: { mode: { enum: string[] }; checkpoint: { enum: string[] } } };
    expect(new Set(approval.properties.mode.enum)).toEqual(new Set(lifecycle.approval_modes));
    expect(new Set(approval.properties.checkpoint.enum)).toEqual(new Set(lifecycle.approval_checkpoints));
  });
});
