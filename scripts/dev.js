import { spawn } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');

// 1. Locate Python executable (check venv first, then system python)
let pythonPath = 'python';
const venvWin = path.join(rootDir, 'venv', 'Scripts', 'python.exe');
const venvUnix = path.join(rootDir, 'venv', 'bin', 'python');

if (process.platform === 'win32' && fs.existsSync(venvWin)) {
  pythonPath = venvWin;
} else if (fs.existsSync(venvUnix)) {
  pythonPath = venvUnix;
}

console.log(`[DevRunner] Launching Python SOC Engine using: ${pythonPath}`);
const apiProcess = spawn(pythonPath, ['run_api.py'], {
  cwd: rootDir,
  stdio: 'inherit',
});

console.log('[DevRunner] Launching Vite Frontend on http://127.0.0.1:1420...');
const viteBin = path.join(rootDir, 'node_modules', 'vite', 'bin', 'vite.js');
const viteProcess = spawn(process.execPath, [viteBin], {
  cwd: rootDir,
  stdio: 'inherit',
});

function cleanup() {
  console.log('\n[DevRunner] Terminating background processes...');
  try { apiProcess.kill(); } catch (_) {}
  try { viteProcess.kill(); } catch (_) {}
  process.exit();
}

process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);
process.on('exit', cleanup);
