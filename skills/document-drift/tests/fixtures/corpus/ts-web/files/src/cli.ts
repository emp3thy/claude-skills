import { Command } from "commander";
import { buildBundle } from "./build";

const program = new Command("web");

program
  .command("build")
  .description("bundle the app")
  .option("--out-dir <dir>", "directory to write the bundle to", "dist")
  .option("--watch", "rebuild when a source file changes")
  .option("--sourcemap", "write source maps next to the bundle")
  .option("--minify", "minify the bundle")
  .action((options) => buildBundle(options));

program
  .command("serve")
  .description("serve the bundle locally")
  .action(() => import("./server").then((server) => server.start()));

program.parse();
