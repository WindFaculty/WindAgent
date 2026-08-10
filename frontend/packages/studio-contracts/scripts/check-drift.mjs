// Contract drift check (C0 CI-local command).
//
// Regenerates the TypeScript contract types into a temp directory and fails when
// the committed src/generated/ output differs from the frozen schemas. Any change
// to schemas/ requires `npm run generate:contracts` in the same commit.
import { spawnSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { promises as fs } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const pkgDir = path.join(here, "..");
const generatedDir = path.join(pkgDir, "src", "generated");
const generator = path.join(here, "generate-contracts.mjs");

const tempDir = await fs.mkdtemp(path.join(tmpdir(), "studio-contracts-drift-"));
const res = spawnSync("node", [generator], {
  encoding: "utf8",
  env: { ...process.env, OVERRIDE_GENERATED_DIR: tempDir },
});
if (res.status !== 0) {
  console.error(res.stdout);
  console.error(res.stderr);
  process.exit(1);
}

const committedFiles = readdirSync(generatedDir).sort();
const regeneratedFiles = readdirSync(tempDir).sort();

const diffs = [];
for (const file of committedFiles) {
  if (!regeneratedFiles.includes(file)) {
    diffs.push(`missing from regenerated output: ${file}`);
    continue;
  }
  const a = readFileSync(path.join(generatedDir, file), "utf8");
  const b = readFileSync(path.join(tempDir, file), "utf8");
  if (a !== b) {
    diffs.push(`drift in ${file}`);
  }
}
for (const file of regeneratedFiles) {
  if (!committedFiles.includes(file)) {
    diffs.push(`untracked regenerated output: ${file}`);
  }
}

if (diffs.length > 0) {
  console.error(`CONTRACT DRIFT: ${diffs.length} difference(s) between schemas/ and src/generated/.`);
  for (const d of diffs) console.error(`  - ${d}`);
  console.error("Run `npm run generate:contracts` and commit the regenerated types.");
  process.exit(1);
}
console.log(`OK: ${committedFiles.length} generated contract type files match schemas/`);
await fs.rm(tempDir, { recursive: true, force: true });
