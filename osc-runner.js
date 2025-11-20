#!/usr/bin/env node
import { readFileSync, watch } from 'fs';
import { repl, evalScope } from '@strudel/core';
import { transpiler } from '@strudel/transpiler';
import * as core from '@strudel/core';
import * as mini from '@strudel/mini';
import * as osc from '@strudel/osc';

const filePath = process.argv[2] || 'src/strudel/hello.str';

console.log('╔════════════════════════════════════════════╗');
console.log('║   Strudel OSC Runner (TidalCycles mode)   ║');
console.log('╚════════════════════════════════════════════╝\n');

console.log('Prerequisites:');
console.log('1. Start SuperCollider and run: SuperDirt.start');
console.log('2. Start OSC server: npm run osc-server');
console.log('3. Add .osc() to your pattern in .str file\n');

console.log(`Watching: ${filePath}`);
console.log('Press Ctrl+C to stop\n');

// Register Strudel functions in eval scope
evalScope(
  core,
  mini,
  osc,
);

// Initialize Strudel REPL
const startTime = performance.now() / 1000;
const scheduler = repl({
  transpiler,
  getTime: () => performance.now() / 1000 - startTime,
});

let isEvaluating = false;

async function runFile() {
  if (isEvaluating) return;
  isEvaluating = true;

  try {
    const code = readFileSync(filePath, 'utf-8');
    const timestamp = new Date().toLocaleTimeString();

    console.log(`[${timestamp}] Evaluating ${filePath}...`);
    console.log('─'.repeat(50));
    console.log(code.trim());
    console.log('─'.repeat(50));

    // Evaluate the code
    await scheduler.evaluate(code);

    console.log('✓ Pattern sent to SuperDirt\n');
  } catch (error) {
    console.error('✗ Error:', error.message);
    console.error(error.stack);
  } finally {
    isEvaluating = false;
  }
}

// Initial run
await runFile();

// Watch for file changes
watch(filePath, async (eventType) => {
  if (eventType === 'change') {
    await runFile();
  }
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\nStopping...');
  scheduler.stop();
  process.exit(0);
});
