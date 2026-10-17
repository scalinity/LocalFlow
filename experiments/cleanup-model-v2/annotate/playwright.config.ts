import { defineConfig } from '@playwright/test';
export default defineConfig({testDir:'./scripts',testMatch:'*.spec.ts',outputDir:'verification/playwright',workers:1,reporter:[['list']],use:{baseURL:'http://localhost:1431',headless:true,channel:'chrome',viewport:{width:1100,height:800},colorScheme:'light',reducedMotion:'reduce',trace:'off'}});
