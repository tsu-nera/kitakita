// VS Code Strudel extension bundle - Latest version
// This replaces the old strudel.js (v0.8.1) with latest Strudel (v1.2+)

import { initStrudel, evaluate, hush, getAudioContext, samples } from '@strudel/web';

// Setup global vscode API if available
const vscode = typeof acquireVsCodeApi !== 'undefined' ? acquireVsCodeApi() : null;

let currentPattern = '';
let isInitialized = false;

// Send message to VS Code extension
function sendMessage(type, value) {
  if (vscode) {
    vscode.postMessage({ type, value });
  }
  console.log(`[Strudel] ${type}:`, value);
}

// Initialize Strudel
async function initAudio() {
  if (isInitialized) {
    sendMessage('status', 'connected');
    return true;
  }

  try {
    sendMessage('log', 'Initializing Strudel (latest version)...');

    // Initialize Strudel with default samples
    await initStrudel({
      prebake: () => samples('github:tidalcycles/Dirt-Samples'),
    });

    // Check if audio context is running
    const ctx = getAudioContext();
    if (ctx && ctx.state === 'running') {
      isInitialized = true;
      sendMessage('status', 'connected');
      sendMessage('log', '✓ Strudel initialized successfully with latest version');
      return true;
    } else {
      sendMessage('warning', 'Audio context not running. Click to start audio.');
      return false;
    }
  } catch (error) {
    sendMessage('error', `Failed to initialize Strudel: ${error.message}`);
    console.error(error);
    return false;
  }
}

// Update pattern code
function updatePattern(code) {
  try {
    currentPattern = code;
    sendMessage('log', `Pattern updated: ${code.substring(0, 50)}${code.length > 50 ? '...' : ''}`);
  } catch (error) {
    sendMessage('error', `Failed to update pattern: ${error.message}`);
  }
}

// Play pattern
async function playPattern() {
  if (!isInitialized) {
    sendMessage('warning', 'Strudel not initialized. Please connect audio first.');
    return;
  }

  if (!currentPattern || currentPattern.trim().length === 0) {
    sendMessage('warning', 'No pattern to play');
    return;
  }

  try {
    sendMessage('log', 'Evaluating pattern...');

    // Evaluate the pattern using @strudel/web
    await evaluate(currentPattern);

    sendMessage('status', 'playing');
    sendMessage('log', '✓ Pattern is playing');
  } catch (error) {
    sendMessage('error', `Failed to play pattern: ${error.message}`);
    sendMessage('status', 'stopped');
    console.error(error);
  }
}

// Stop playback
function stopPattern() {
  try {
    hush();
    sendMessage('status', 'stopped');
    sendMessage('log', 'Playback stopped');
  } catch (error) {
    sendMessage('error', `Failed to stop pattern: ${error.message}`);
  }
}

// DOM ready handler
if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    const connectBtn = document.getElementById('strudel-connect');
    const infoEl = document.getElementById('strudel-info');

    if (connectBtn) {
      connectBtn.addEventListener('click', async () => {
        connectBtn.style.display = 'none';
        infoEl.style.display = 'block';
        infoEl.textContent = 'Connecting audio...';

        const success = await initAudio();
        if (success) {
          infoEl.textContent = '✓ Audio connected';
        } else {
          infoEl.textContent = '✗ Failed to connect audio';
          connectBtn.style.display = 'block';
        }
      });
    }

    // Listen for messages from VS Code extension
    window.addEventListener('message', (event) => {
      const message = event.data;
      switch (message.command) {
        case 'update':
          updatePattern(message.data);
          break;
        case 'play':
          playPattern();
          break;
        case 'stop':
          stopPattern();
          break;
        default:
          console.error('Unknown command:', message.command);
      }
    });

    sendMessage('log', 'Strudel webview loaded (Latest version)');
  });
}
