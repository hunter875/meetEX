import {build} from 'esbuild';
await build({entryPoints:['src/content/index.ts'],bundle:true,outfile:'dist/content.js',format:'iife',target:'chrome116'});
