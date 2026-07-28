import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

function sourceFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) ? [path] : [];
  });
}

test("frontend source does not use native window.prompt", () => {
  const offenders = sourceFiles(join(process.cwd(), "src")).filter((path) =>
    readFileSync(path, "utf8").includes("window.prompt("),
  );
  assert.deepEqual(offenders, []);
});
