import { spawn } from 'node:child_process';

const DEV_SERVER_URL = 'http://localhost:3000';
const SERVER_TIMEOUT_MS = 30_000;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function isServerReady() {
  try {
    const response = await fetch(DEV_SERVER_URL, { method: 'GET' });
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForServer(timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isServerReady()) {
      return true;
    }
    await sleep(500);
  }
  return false;
}

function spawnCommand(command) {
  return spawn(command, {
    stdio: 'inherit',
    shell: true,
  });
}

let viteProcess = null;

if (!(await isServerReady())) {
  viteProcess = spawnCommand('npm run ui:dev');
  const ready = await waitForServer(SERVER_TIMEOUT_MS);
  if (!ready) {
    viteProcess.kill();
    throw new Error(`Vite dev server did not become ready on ${DEV_SERVER_URL} within ${SERVER_TIMEOUT_MS}ms.`);
  }
}

const electronProcess = spawnCommand('npx electron .');

const shutdown = () => {
  if (viteProcess && !viteProcess.killed) {
    viteProcess.kill();
  }
};

electronProcess.on('exit', (code) => {
  shutdown();
  process.exit(code ?? 0);
});

electronProcess.on('error', (error) => {
  shutdown();
  throw error;
});

process.on('SIGINT', () => {
  shutdown();
  electronProcess.kill();
});

process.on('SIGTERM', () => {
  shutdown();
  electronProcess.kill();
});
