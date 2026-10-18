import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./e2e',fullyParallel:false,workers:1,timeout:60000,expect:{timeout:12000},reporter:[['list'],['json',{outputFile:process.env.MEET_E2E_RESULTS_FILE||'docs/evidence/e2e-results.json'}]],use:{trace:'retain-on-failure'},outputDir:'test-results'});
