import { build } from "esbuild";

await build({
  entryPoints: ["src/browser.ts"],
  bundle: true,
  format: "iife",
  globalName: "GoRpc",
  outfile: "dist/browser/go-rpc.js",
  platform: "browser",
  target: ["es2020"],
  sourcemap: true,
});
