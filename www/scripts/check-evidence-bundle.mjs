import { readFileSync, readdirSync } from "node:fs";
import { gzipSync } from "node:zlib";

const assetsDirectory = new URL("../dist/assets/", import.meta.url);
const matches = readdirSync(assetsDirectory).filter((name) => name.startsWith("plotly-cartesian.min-") && name.endsWith(".js"));

if (matches.length !== 1) {
  throw new Error(`Expected one lazy evidence-chart bundle; found ${matches.length}.`);
}

const bytes = readFileSync(new URL(matches[0], assetsDirectory));
const gzipBytes = gzipSync(bytes).byteLength;
const budget = { minified: 1_600_000, gzip: 550_000 };

if (bytes.byteLength > budget.minified || gzipBytes > budget.gzip) {
  throw new Error(
    `Evidence-chart bundle exceeds budget: ${bytes.byteLength} bytes minified, ${gzipBytes} bytes gzip.`,
  );
}

console.log(`Evidence-chart bundle: ${bytes.byteLength} bytes minified, ${gzipBytes} bytes gzip.`);
