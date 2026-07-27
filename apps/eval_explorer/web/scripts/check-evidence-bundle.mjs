import { readFileSync, readdirSync } from "node:fs";
import { gzipSync } from "node:zlib";

const assetsDirectory = new URL("../dist/assets/", import.meta.url);
const matches = readdirSync(assetsDirectory).filter((name) => name.startsWith("plotly-cartesian.min-") && name.endsWith(".js"));

if (matches.length === 0) {
  const projectAdapter = readFileSync(
    new URL("../../../../use_case/explorer/adapter.tsx", import.meta.url),
    "utf8",
  );
  if (projectAdapter.includes("unconfiguredUseCaseAdapter")) {
    console.log("Neutral use-case adapter: no evidence-chart bundle expected.");
    process.exit(0);
  }
}

if (matches.length !== 1) {
  throw new Error(`Expected one lazy evidence-chart bundle; found ${matches.length}.`);
}

const stylesheets = readdirSync(assetsDirectory).filter(
  (name) => name.startsWith("index-") && name.endsWith(".css"),
);
if (stylesheets.length !== 1) {
  throw new Error(`Expected one explorer stylesheet; found ${stylesheets.length}.`);
}
const stylesheet = readFileSync(new URL(stylesheets[0], assetsDirectory), "utf8");
const fullscreenUtilities = [
  ".fixed{position:fixed}",
  ".inset-0{inset:0}",
  ".z-\\[100\\]{z-index:100}",
  ".h-screen{height:100vh}",
];
const missingUtilities = fullscreenUtilities.filter(
  (utility) => !stylesheet.includes(utility),
);
if (missingUtilities.length) {
  throw new Error(
    "Project evidence fullscreen styles are missing from the production CSS: "
      + missingUtilities.join(", "),
  );
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
console.log("Project evidence fullscreen styles: verified.");
