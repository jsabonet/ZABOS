const fs = require("node:fs/promises");
const path = require("node:path");
const { bundle } = require("@remotion/bundler");
const { renderMedia, selectComposition } = require("@remotion/renderer");

function readArguments(args) {
  const values = {};
  for (let index = 2; index < args.length; index += 2) {
    const key = args[index];
    const value = args[index + 1];
    if (!["--props", "--output"].includes(key) || !value) {
      throw new Error("Usage: node scripts/render.cjs --props <file> --output <file>");
    }
    values[key] = value;
  }
  if (!values["--props"] || !values["--output"]) {
    throw new Error("Both --props and --output are required.");
  }
  return values;
}

async function main() {
  const args = readArguments(process.argv);
  const projectDir = path.resolve(__dirname, "..");
  const entryPoint = path.join(projectDir, "src", "index.ts");
  const inputProps = JSON.parse(await fs.readFile(args["--props"], "utf8"));
  const outputLocation = path.resolve(args["--output"]);
  const bundled = await bundle({
    entryPoint,
    outDir: path.join(projectDir, ".cache", "bundle"),
    webpackOverride: (config) => config,
  });
  const composition = await selectComposition({
    serveUrl: bundled,
    id: "ShortVideo",
    inputProps,
  });
  if (composition.durationInFrames < 1) {
    throw new Error("The video props do not produce a valid composition duration.");
  }
  await renderMedia({
    composition,
    serveUrl: bundled,
    codec: "h264",
    outputLocation,
    inputProps,
    overwrite: true,
  });
  process.stdout.write(`Rendered ${outputLocation}\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
