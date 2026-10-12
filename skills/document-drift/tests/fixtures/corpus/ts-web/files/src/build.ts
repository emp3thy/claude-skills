export interface BuildOptions {
  outDir: string;
  watch?: boolean;
  sourcemap?: boolean;
  minify?: boolean;
}

export async function buildBundle(options: BuildOptions): Promise<void> {
  console.log(`bundling into ${options.outDir}`);
}
