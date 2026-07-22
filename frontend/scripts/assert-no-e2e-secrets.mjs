import fs from "node:fs";
import path from "node:path";

const roots = ["test-results/playwright", "test-results/shared-playwright", "test-results/playwright-report", "test-results/shared-playwright-report"];
const secrets = [process.env.PID_AGENT_E2E_SHARED_TOKEN ?? "pid-agent-shared-e2e-token"];
const textExtensions = new Set([".json", ".txt", ".html", ".xml", ".log", ".jsonl", ".md"]);
const leaks = [];

function visit(target) {
  if (!fs.existsSync(target)) return;
  const stat = fs.statSync(target);
  if (stat.isDirectory()) {
    for (const entry of fs.readdirSync(target)) visit(path.join(target, entry));
    return;
  }
  if (!textExtensions.has(path.extname(target).toLowerCase())) return;
  const body = fs.readFileSync(target, "utf8");
  if (secrets.some((secret) => body.includes(secret))) leaks.push(target);
}

for (const root of roots) visit(root);
if (leaks.length) {
  console.error(`E2E credential leaked into artifacts: ${leaks.join(", ")}`);
  process.exit(1);
}
console.log("No E2E credentials found in text artifacts.");
