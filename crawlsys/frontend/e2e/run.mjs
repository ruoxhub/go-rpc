import { spawn } from "node:child_process";
import { rm } from "node:fs/promises";
import { resolve } from "node:path";

const child = spawn("playwright test", {
  cwd: process.cwd(),
  env: process.env,
  shell: true,
  stdio: "inherit",
});

const exitCode = await new Promise((resolveExit, reject) => {
  child.once("error", reject);
  child.once("exit", (code) => resolveExit(code ?? 1));
});

await rm(resolve(".e2e/crawler.sqlite3"), { force: true });
process.exitCode = exitCode;
