import path from 'node:path';
import fs from 'node:fs';
import fsPromises from 'node:fs/promises';
import dns from 'node:dns/promises';
import https from 'node:https';
import { createHash, randomUUID } from 'node:crypto';
import net from 'node:net';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import electron from 'electron';
import { chatCompletion, streamCompletion, generateImage } from './services/aiService.js';
import { testProviderConnection } from './services/providerConnectionService.js';
import { ALLOWED_TABLES, openDb, closeDb, closeAllDbs, upsertEntity, getAllEntities, deleteEntity, migrateFromJson, indexEntity, searchEntities } from './db.js';

const { app, BrowserWindow, dialog, ipcMain } = electron;

if (process.env.NARRATIVE_IDE_USER_DATA) {
  app.setPath('userData', process.env.NARRATIVE_IDE_USER_DATA);
}

// ── Sidecar process management ────────────────────────────────────────────────

const PID_DIR = path.join(os.homedir(), '.narrative-ide', 'processes');
/** Maps projectRoot → spawned ChildProcess */
const sidecarProcesses = new Map();
/** Maps projectRoot → sidecar port number */
const sidecarPorts = new Map();
/** Maps projectRoot → the in-flight readiness check for a spawned sidecar. */
const sidecarStartupPromises = new Map();
/** Maps projectRoot → an in-flight graceful/forced termination. */
const sidecarShutdownPromises = new Map();
/** Maps BrowserWindow → projectRoot for sidecar cleanup. */
const windowProjectMap = new Map();
/** Maps renderer WebContents IDs → their selected project session. */
const senderProjectRoots = new Map();
/** Maps renderer WebContents IDs to one-time local files selected through a native dialog. */
const senderSourceGrants = new Map();
/** Maps renderer WebContents IDs to the active durable runtime SSE request. */
const runtimeEventStreams = new Map();
/** Maps renderer WebContents IDs to the active legacy workflow SSE request. */
const workflowEventStreams = new Map();
const MAX_PROJECT_FILE_BYTES = 64 * 1024 * 1024;
const MAX_PORTRAIT_BYTES = 16 * 1024 * 1024;
const SOURCE_GRANT_TTL_MS = 5 * 60 * 1000;
const SIDECAR_STARTUP_TIMEOUT_MS = 15_000;
const SIDECAR_HEALTH_REQUEST_TIMEOUT_MS = 750;
const SIDECAR_SHUTDOWN_GRACE_MS = 3_000;
const SIDECAR_SHUTDOWN_KILL_MS = 2_000;

async function canonicalProjectRoot(projectRoot) {
  if (typeof projectRoot !== 'string' || projectRoot.includes('\0') || !path.isAbsolute(projectRoot)) {
    throw new Error('Invalid projectRoot');
  }
  try {
    const root = await fsPromises.realpath(projectRoot);
    if (!(await fsPromises.stat(root)).isDirectory()) throw new Error('not a directory');
    return root;
  } catch {
    throw new Error('Invalid projectRoot');
  }
}

async function registerProjectRoot(event, projectRoot, { allowProjectChild = false } = {}) {
  const root = await canonicalProjectRoot(projectRoot);
  senderProjectRoots.set(event.sender.id, { root, allowProjectChild });
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) windowProjectMap.set(win, root);
  return root;
}

async function requireProjectRoot(event, projectRoot) {
  const root = await canonicalProjectRoot(projectRoot);
  const session = senderProjectRoots.get(event.sender.id);
  if (session?.root === root) return root;
  // Creating a project selects its parent before the new project directory exists.
  if (session?.allowProjectChild && path.dirname(root) === session.root) {
    senderProjectRoots.set(event.sender.id, { root, allowProjectChild: false });
    const win = BrowserWindow.fromWebContents(event.sender);
    if (win) windowProjectMap.set(win, root);
    return root;
  }
  if (!session) {
    throw new Error('Unauthorized projectRoot');
  }
  throw new Error('Unauthorized projectRoot');
}

function isPathWithin(root, target) {
  const relative = path.relative(root, target);
  return relative === '' || (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative));
}

function requireCurrentProjectRoot(event) {
  const session = senderProjectRoots.get(event.sender.id);
  if (!session) throw new Error('Unauthorized projectRoot');
  const root = fs.realpathSync(session.root);
  if (root !== session.root || !fs.statSync(root).isDirectory()) {
    throw new Error('Authorized project root changed');
  }
  return { session, root };
}

function findExistingAncestor(target) {
  let ancestor = target;
  while (!fs.existsSync(ancestor)) {
    const parent = path.dirname(ancestor);
    if (parent === ancestor) throw new Error('Invalid project file path');
    ancestor = parent;
  }
  return ancestor;
}

function authorizeProjectFilePath(event, filePath, { allowCreate = false, requireFile = false } = {}) {
  if (typeof filePath !== 'string' || filePath.includes('\0') || !path.isAbsolute(filePath)) throw new Error('Invalid project file path');
  let { session, root } = requireCurrentProjectRoot(event);
  const selectedParent = session.root;
  const requestedTarget = path.resolve(filePath);
  const ancestor = findExistingAncestor(requestedTarget);
  const resolvedAncestor = fs.realpathSync(ancestor);
  // Preserve the target's suffix while canonicalizing a macOS /tmp-style alias.
  const target = path.resolve(resolvedAncestor, path.relative(ancestor, requestedTarget));
  if (session.allowProjectChild && allowCreate && path.dirname(target) === root) {
    const win = BrowserWindow.fromWebContents(event.sender);
    session = { root: target, allowProjectChild: false };
    senderProjectRoots.set(event.sender.id, session);
    if (win) windowProjectMap.set(win, target);
    root = target;
  }
  if (!isPathWithin(root, target)) throw new Error('Project file path escapes authorized root');

  const creatingAuthorizedRoot = allowCreate && target === root && root !== selectedParent;
  if (!isPathWithin(root, resolvedAncestor) && !(creatingAuthorizedRoot && isPathWithin(selectedParent, resolvedAncestor))) {
    throw new Error('Project file path resolves outside authorized root');
  }
  if (fs.existsSync(target)) {
    const stat = fs.lstatSync(target);
    if (stat.isSymbolicLink()) throw new Error('Project file path must not be a symbolic link');
    const resolvedTarget = fs.realpathSync(target);
    if (!isPathWithin(root, resolvedTarget)) throw new Error('Project file path resolves outside authorized root');
    if (requireFile && !stat.isFile()) throw new Error('Project file does not exist');
  } else if (requireFile) {
    throw new Error('Project file does not exist');
  }
  return { target, root };
}

function verifyProjectFilePath(event, filePath, options = {}) {
  // Revalidate immediately before the filesystem operation to narrow rename/symlink races.
  return authorizeProjectFilePath(event, filePath, options);
}

function decodeBase64(data) {
  if (typeof data !== 'string' || data.length % 4 !== 0 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(data)) {
    throw new Error('Invalid project file base64 data');
  }
  const bytes = Buffer.from(data, 'base64');
  if (bytes.length > MAX_PROJECT_FILE_BYTES) throw new Error('Project file is too large');
  return bytes;
}

function readProjectFileData(target, encoding) {
  const stat = fs.lstatSync(target);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Project file does not exist');
  if (stat.size > MAX_PROJECT_FILE_BYTES) throw new Error('Project file is too large');
  const data = fs.readFileSync(target);
  return encoding === 'base64' ? data.toString('base64') : data.toString('utf8');
}

function fsyncDirectory(directory) {
  const descriptor = fs.openSync(directory, fs.constants.O_RDONLY | (fs.constants.O_DIRECTORY || 0));
  try {
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
}

function createTemporaryFile(directory, target) {
  const noFollow = fs.constants.O_NOFOLLOW || 0;
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const temporary = path.join(directory, `.${path.basename(target)}.${process.pid}.${Date.now()}.${attempt}.tmp`);
    try {
      const descriptor = fs.openSync(temporary, fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | noFollow, 0o600);
      return { temporary, descriptor };
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
    }
  }
  throw new Error('Could not create project file temporary');
}

function writeProjectFileAtomically(event, targetPath, data) {
  if (!Buffer.isBuffer(data) && typeof data !== 'string') throw new Error('Invalid project file data');
  const byteLength = Buffer.isBuffer(data) ? data.length : Buffer.byteLength(data, 'utf8');
  if (byteLength > MAX_PROJECT_FILE_BYTES) throw new Error('Project file is too large');

  const { target, root } = verifyProjectFilePath(event, targetPath, { allowCreate: true });
  const directory = path.dirname(target);
  const resolvedDirectory = fs.realpathSync(directory);
  if (!isPathWithin(root, resolvedDirectory)) throw new Error('Project file path resolves outside authorized root');

  let temporary;
  let descriptor;
  try {
    ({ temporary, descriptor } = createTemporaryFile(resolvedDirectory, target));
    fs.writeFileSync(descriptor, data);
    fs.fsyncSync(descriptor);
    fs.closeSync(descriptor);
    descriptor = undefined;

    // Check root, parent, and any existing destination again just before commit.
    verifyProjectFilePath(event, target, { allowCreate: true });
    fs.renameSync(temporary, target);
    fsyncDirectory(resolvedDirectory);
  } catch (error) {
    if (descriptor !== undefined) {
      try { fs.closeSync(descriptor); } catch { /* ignore close cleanup failure */ }
    }
    if (temporary) {
      try { fs.unlinkSync(temporary); } catch { /* ignore temporary cleanup failure */ }
    }
    throw error;
  }
}

function handleProjectFileSync(event, operation, payload = {}) {
  try {
    const allowCreate = operation === 'mkdir' || operation === 'write' || operation === 'rename';
    const { target } = authorizeProjectFilePath(event, payload.path, { allowCreate, requireFile: ['read', 'unlink', 'copy', 'rename'].includes(operation) });
    switch (operation) {
      case 'exists': {
        const checked = verifyProjectFilePath(event, target);
        return { ok: true, value: fs.existsSync(checked.target) };
      }
      case 'read': {
        const { target: checked } = verifyProjectFilePath(event, target, { requireFile: true });
        const encoding = payload.encoding === 'base64' ? 'base64' : payload.encoding === 'utf8' || payload.encoding === undefined ? 'utf8' : null;
        if (!encoding) throw new Error('Invalid project file encoding');
        return { ok: true, value: readProjectFileData(checked, encoding) };
      }
      case 'mkdir': {
        fs.mkdirSync(target, { recursive: true });
        verifyProjectFilePath(event, target);
        return { ok: true };
      }
      case 'readdir': {
        const { target: checked } = verifyProjectFilePath(event, target);
        if (!fs.lstatSync(checked).isDirectory()) throw new Error('Project directory does not exist');
        return { ok: true, value: fs.readdirSync(checked) };
      }
      case 'unlink': {
        const { target: checked } = verifyProjectFilePath(event, target, { requireFile: true });
        fs.unlinkSync(checked);
        fsyncDirectory(path.dirname(checked));
        return { ok: true };
      }
      case 'realpath': {
        const { target: checked } = verifyProjectFilePath(event, target);
        return { ok: true, value: fs.realpathSync(checked) };
      }
      case 'copy': {
        const { target: source } = verifyProjectFilePath(event, target, { requireFile: true });
        const sourceStat = fs.lstatSync(source);
        if (!sourceStat.isFile() || sourceStat.size > MAX_PROJECT_FILE_BYTES) throw new Error('Project file is too large');
        const { target: destination } = authorizeProjectFilePath(event, payload.destination, { allowCreate: true });
        writeProjectFileAtomically(event, destination, fs.readFileSync(source));
        return { ok: true };
      }
      case 'rename': {
        const { target: source, root } = verifyProjectFilePath(event, target, { requireFile: true });
        const { target: destination } = authorizeProjectFilePath(event, payload.destination, { allowCreate: true });
        verifyProjectFilePath(event, destination, { allowCreate: true });
        fs.renameSync(source, destination);
        fsyncDirectory(path.dirname(destination));
        if (path.dirname(source) !== path.dirname(destination) && isPathWithin(root, path.dirname(source))) fsyncDirectory(path.dirname(source));
        return { ok: true };
      }
      case 'write': {
        if (typeof payload.data !== 'string') throw new Error('Invalid project file data');
        const encoding = payload.encoding === 'base64' ? 'base64' : payload.encoding === 'utf8' || payload.encoding === undefined ? 'utf8' : null;
        if (!encoding) throw new Error('Invalid project file encoding');
        writeProjectFileAtomically(event, target, encoding === 'base64' ? decodeBase64(payload.data) : payload.data);
        return { ok: true };
      }
      default: throw new Error('Unsupported project file operation');
    }
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'Project file operation failed' };
  }
}

function requireIdentifier(value, name) {
  if (typeof value !== 'string' || !value.trim() || value.length > 256) {
    throw new Error(`Invalid ${name}`);
  }
  return value;
}

function requirePlainObject(value, name) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`Invalid ${name}`);
  }
  return value;
}

function isPublicPortraitUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && (url.port === '' || url.port === '443');
  } catch {
    return false;
  }
}

function isPublicPortraitAddress(address) {
  const normalized = address.toLowerCase().replace(/^\[|\]$/g, '');
  const family = net.isIP(normalized);
  if (family === 4) {
    const [first, second] = normalized.split('.').map(Number);
    return first >= 1 && first <= 223
      && first !== 10 && first !== 127
      && !(first === 100 && second >= 64 && second <= 127)
      && !(first === 169 && second === 254)
      && !(first === 172 && second >= 16 && second <= 31)
      && !(first === 192 && (second === 0 || second === 168))
      && !(first === 198 && (second === 18 || second === 19));
  }
  if (family !== 6) return false;
  const mappedIpv4 = normalized.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  if (mappedIpv4) return isPublicPortraitAddress(mappedIpv4[1]);
  return normalized !== '::' && normalized !== '::1'
    && !normalized.startsWith('fc') && !normalized.startsWith('fd')
    && !/^fe[89ab]/.test(normalized) && !normalized.startsWith('2001:db8');
}

async function resolvePublicPortraitAddresses(url) {
  const hostname = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (hostname === 'localhost' || hostname.endsWith('.localhost')) throw new Error('Portrait URL must resolve to a public address');
  const literalFamily = net.isIP(hostname);
  const addresses = literalFamily
    ? [{ address: hostname, family: literalFamily }]
    : await dns.lookup(hostname, { all: true, verbatim: true });
  if (addresses.length === 0 || addresses.some(({ address }) => !isPublicPortraitAddress(address))) {
    throw new Error('Portrait URL must resolve only to public addresses');
  }
  return addresses;
}

async function requestPublicPortrait(url) {
  if (!isPublicPortraitUrl(url.href)) throw new Error('Portrait URL must use public HTTPS');
  const addresses = await resolvePublicPortraitAddresses(url);
  const selectedAddress = addresses[0];
  return await new Promise((resolve, reject) => {
    const request = https.request(url, {
      lookup: (_hostname, _options, callback) => callback(null, selectedAddress.address, selectedAddress.family),
      timeout: 15_000,
    }, resolve);
    request.once('timeout', () => request.destroy(new Error('Portrait download timed out')));
    request.once('error', reject);
    request.end();
  });
}

async function downloadPublicPortrait(initialUrl) {
  let currentUrl = new URL(initialUrl);
  for (let redirectCount = 0; redirectCount <= 4; redirectCount += 1) {
    const response = await requestPublicPortrait(currentUrl);
    if ([301, 302, 303, 307, 308].includes(response.statusCode)) {
      const location = response.headers.location;
      response.resume();
      if (!location || redirectCount === 4) throw new Error('Portrait URL redirect is invalid');
      currentUrl = new URL(location, currentUrl);
      continue;
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      response.resume();
      throw new Error(`Failed to download image: ${response.statusCode}`);
    }
    const chunks = [];
    let total = 0;
    for await (const chunk of response) {
      total += chunk.length;
      if (total > MAX_PORTRAIT_BYTES) {
        response.destroy(new Error('Portrait image is too large'));
        throw new Error('Portrait image is too large');
      }
      chunks.push(chunk);
    }
    return Buffer.concat(chunks);
  }
  throw new Error('Portrait URL redirect is invalid');
}

async function registerSourceGrants(event, filePaths) {
  const now = Date.now();
  const grants = new Map();
  const selectedPaths = [];
  for (const filePath of filePaths) {
    if (typeof filePath !== 'string' || filePath.includes('\0') || !path.isAbsolute(filePath)) continue;
    const canonicalPath = await fsPromises.realpath(filePath);
    const stat = await fsPromises.lstat(canonicalPath);
    if (!stat.isFile() || stat.isSymbolicLink()) continue;
    grants.set(canonicalPath, now + SOURCE_GRANT_TTL_MS);
    selectedPaths.push(canonicalPath);
  }
  senderSourceGrants.set(event.sender.id, grants);
  return selectedPaths;
}

async function consumePortraitSourceGrant(event, source) {
  if (typeof source !== 'string' || source.includes('\0')) throw new Error('Invalid portrait source');
  let sourcePath;
  try {
    sourcePath = source.startsWith('file:') ? fileURLToPath(new URL(source)) : source;
  } catch {
    throw new Error('Invalid portrait source');
  }
  if (!path.isAbsolute(sourcePath)) throw new Error('Invalid portrait source');
  const canonicalPath = await fsPromises.realpath(sourcePath);
  const grants = senderSourceGrants.get(event.sender.id);
  const expiresAt = grants?.get(canonicalPath);
  if (!expiresAt || expiresAt < Date.now()) throw new Error('Portrait source was not selected through the file dialog');
  grants.delete(canonicalPath);
  if (grants.size === 0) senderSourceGrants.delete(event.sender.id);
  const stat = await fsPromises.lstat(canonicalPath);
  if (!stat.isFile() || stat.isSymbolicLink()) throw new Error('Portrait source is not a regular file');
  if (stat.size > MAX_PORTRAIT_BYTES) throw new Error('Portrait image is too large');
  return canonicalPath;
}

async function getPortraitDestination(event, projectRoot, characterId) {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (!/^[a-zA-Z0-9_-]+$/.test(characterId)) throw new Error('Invalid portrait payload');
  const portraitsDir = path.join(projectRoot, 'characters', 'portraits');
  await fsPromises.mkdir(portraitsDir, { recursive: true });
  const resolvedPortraitsDir = await fsPromises.realpath(portraitsDir);
  if (!isPathWithin(projectRoot, resolvedPortraitsDir)) throw new Error('Portrait directory escapes authorized root');
  const filePath = path.join(resolvedPortraitsDir, `${characterId}-${randomUUID()}.png`);
  return { filePath, portraitsDir: resolvedPortraitsDir, projectRoot };
}

async function writePortraitDestination(destination, data) {
  const { filePath, portraitsDir, projectRoot } = destination;
  const flags = fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | (fs.constants.O_NOFOLLOW || 0);
  const file = await fsPromises.open(filePath, flags, 0o600);
  try {
    const [handleStat, pathStat, resolvedFilePath, currentPortraitsDir] = await Promise.all([
      file.stat(),
      fsPromises.lstat(filePath),
      fsPromises.realpath(filePath),
      fsPromises.realpath(portraitsDir),
    ]);
    if (
      !handleStat.isFile()
      || !pathStat.isFile()
      || pathStat.isSymbolicLink()
      || handleStat.dev !== pathStat.dev
      || handleStat.ino !== pathStat.ino
      || currentPortraitsDir !== portraitsDir
      || resolvedFilePath !== filePath
      || path.dirname(resolvedFilePath) !== portraitsDir
      || !isPathWithin(projectRoot, resolvedFilePath)
    ) throw new Error('Portrait destination changed before write');
    await file.writeFile(data);
    await file.sync();
  } finally {
    await file.close();
  }
}

async function showOpenDialog(options) {
  if (process.env.NARRATIVE_IDE_RUNTIME_SMOKE) {
    const filePaths = options.properties.includes('openDirectory')
      ? [process.env.NARRATIVE_IDE_SMOKE_PROJECT_ROOT || '/tmp/narrative-ide-smoke-project']
      : [process.env.NARRATIVE_IDE_SMOKE_SOURCE_PATH || '/tmp/narrative-ide-smoke-source.txt'];
    return { canceled: false, filePaths };
  }
  return dialog.showOpenDialog(options);
}

function getSidecarPidFile(projectRoot) {
  fs.mkdirSync(PID_DIR, { recursive: true });
  const projectId = createHash('sha256').update(projectRoot, 'utf8').digest('hex').slice(0, 40);
  return path.join(PID_DIR, `${projectId}.json`);
}

function getLegacySidecarPidFile(projectRoot) {
  const projectId = Buffer.from(projectRoot).toString('base64url').slice(0, 40);
  return path.join(PID_DIR, `${projectId}.json`);
}

function getSidecarPidCandidates(projectRoot) {
  return [...new Set([getSidecarPidFile(projectRoot), getLegacySidecarPidFile(projectRoot)])];
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function isPidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM: process exists but we lack permission (common on macOS for same-user)
    return err.code === 'EPERM';
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchWithTimeout(url, options = {}, timeoutMs = SIDECAR_HEALTH_REQUEST_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function startSidecar(projectRoot) {
  // Check both the collision-resistant identity and the one-version legacy path.
  for (const pidFile of getSidecarPidCandidates(projectRoot)) {
    if (!fs.existsSync(pidFile)) continue;
    try {
      const data = JSON.parse(fs.readFileSync(pidFile, 'utf8'));
      // Legacy IDs can collide on long common path prefixes. Never reuse,
      // terminate, or delete another project's sidecar metadata.
      if (data.projectPath !== projectRoot) continue;
      if (data.pid && isPidAlive(data.pid)) {
        // Sidecar already running — verify it's actually listening
        sidecarPorts.set(projectRoot, data.port);
        if (await waitForSidecarHealth(data.port, SIDECAR_HEALTH_REQUEST_TIMEOUT_MS)) {
          return data.port;
        }
        // Health check failed — kill stale process and respawn
        try { process.kill(data.pid, 'SIGTERM'); } catch { /* ignore */ }
        try { fs.unlinkSync(pidFile); } catch { /* ignore */ }
        sidecarPorts.delete(projectRoot);
      } else {
        // Stale PID — delete and respawn
        fs.unlinkSync(pidFile);
      }
    } catch {
      try { fs.unlinkSync(pidFile); } catch { /* corrupt file — ignore */ }
    }
  }

  // If already spawned in this session, only reuse it after a bounded readiness check.
  const existingPort = sidecarPorts.get(projectRoot);
  if (existingPort && sidecarProcesses.has(projectRoot)) {
    if (await waitForSidecarHealth(existingPort, SIDECAR_HEALTH_REQUEST_TIMEOUT_MS)) return existingPort;
    await stopSidecar(projectRoot);
  }

  const port = await findFreePort();
  const pidFile = getSidecarPidFile(projectRoot);
  const sidecarEntry = path.resolve(__dirname, '../../sidecar/main.py');

  // Resolve Python: prefer venv at sidecar/.venv, then python3 (macOS/Linux), then python (Windows)
  const venvPython = path.resolve(__dirname, '../../sidecar/.venv/bin/python');
  const pythonCmd = fs.existsSync(venvPython) ? venvPython : (process.platform === 'win32' ? 'python' : 'python3');

  const proc = spawn(pythonCmd, [sidecarEntry, '--port', String(port), '--project-path', projectRoot], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
  });
  let startupFailure = null;

  proc.stdout.on('data', (d) => console.log(`[sidecar:${port}]`, d.toString().trim()));
  proc.stderr.on('data', (d) => console.error(`[sidecar:${port}:err]`, d.toString().trim()));
  proc.once('error', (error) => {
    startupFailure = `sidecar_spawn_failed: ${error.message}`;
  });
  proc.on('exit', (code, signal) => {
    console.log(`[sidecar:${port}] exited with code ${code}`);
    if (sidecarProcesses.get(projectRoot) === proc) {
      sidecarProcesses.delete(projectRoot);
      sidecarPorts.delete(projectRoot);
      try { fs.unlinkSync(getSidecarPidFile(projectRoot)); } catch { /* ignore */ }
    }
    if (code !== 0 && signal !== 'SIGTERM' && signal !== 'SIGKILL') {
      startupFailure ??= `sidecar_exited_before_ready: code=${code ?? 'null'} signal=${signal ?? 'none'}`;
      console.error(`[sidecar:${port}] exited before readiness (code ${code}, signal ${signal ?? 'none'})`);
    }
  });

  sidecarProcesses.set(projectRoot, proc);
  sidecarPorts.set(projectRoot, port);

  // Write PID file
  fs.writeFileSync(pidFile, JSON.stringify({ pid: proc.pid, port, projectPath: projectRoot }, null, 2), 'utf8');

  // Do not publish this port until the exact child we spawned is answering /health.
  const ready = await waitForSidecarHealth(port, SIDECAR_STARTUP_TIMEOUT_MS, () => proc.exitCode === null && !proc.killed);
  if (!ready) {
    await stopSidecar(projectRoot);
    throw new Error(startupFailure ?? `sidecar_startup_timeout: /health did not become ready within ${SIDECAR_STARTUP_TIMEOUT_MS}ms`);
  }

  return port;
}

async function spawnSidecar(projectRoot) {
  const pending = sidecarStartupPromises.get(projectRoot);
  if (pending) return pending;
  const startup = startSidecar(projectRoot);
  sidecarStartupPromises.set(projectRoot, startup);
  try {
    return await startup;
  } finally {
    if (sidecarStartupPromises.get(projectRoot) === startup) sidecarStartupPromises.delete(projectRoot);
  }
}

/**
 * Poll the sidecar health endpoint until it responds or we give up.
 * @param {number} port
 * @param {number} timeoutMs - maximum wait before reporting failure
 * @param {() => boolean} isExpectedProcessRunning - validates a just-spawned child
 * @returns {Promise<boolean>} true if healthy
 */
async function waitForSidecarHealth(port, timeoutMs, isExpectedProcessRunning = null) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (isExpectedProcessRunning && !isExpectedProcessRunning()) return false;
    try {
      const res = await fetchWithTimeout(`http://127.0.0.1:${port}/health`);
      if (res.ok) return true;
    } catch { /* not ready yet */ }
    await delay(Math.min(150, Math.max(0, deadline - Date.now())));
  }
  return false;
}

function waitForChildExit(proc, timeoutMs) {
  if (proc.exitCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(done, timeoutMs);
    const onExit = () => done();
    function done() {
      clearTimeout(timer);
      proc.off('exit', onExit);
      resolve();
    }
    proc.once('exit', onExit);
  });
}

async function stopSidecar(projectRoot) {
  const existingShutdown = sidecarShutdownPromises.get(projectRoot);
  if (existingShutdown) return existingShutdown;
  const shutdown = (async () => {
    const proc = sidecarProcesses.get(projectRoot);
    sidecarProcesses.delete(projectRoot);
    sidecarPorts.delete(projectRoot);
    sidecarStartupPromises.delete(projectRoot);
    for (const pidFile of getSidecarPidCandidates(projectRoot)) {
      if (fs.existsSync(pidFile)) {
        try { fs.unlinkSync(pidFile); } catch { /* ignore */ }
      }
    }
    if (proc) {
      try { proc.kill('SIGTERM'); } catch { /* already exited */ }
      await waitForChildExit(proc, SIDECAR_SHUTDOWN_GRACE_MS);
      if (proc.exitCode === null) {
        try { proc.kill('SIGKILL'); } catch { /* already exited */ }
        await waitForChildExit(proc, SIDECAR_SHUTDOWN_KILL_MS);
      }
    }
  })();
  sidecarShutdownPromises.set(projectRoot, shutdown);
  try {
    await shutdown;
  } finally {
    if (sidecarShutdownPromises.get(projectRoot) === shutdown) sidecarShutdownPromises.delete(projectRoot);
  }
}

async function stopAllSidecars() {
  const projectRoots = new Set([...sidecarProcesses.keys(), ...sidecarShutdownPromises.keys()]);
  await Promise.all([...projectRoots].map((projectRoot) => stopSidecar(projectRoot)));
}

async function getReadySidecarPort(projectRoot) {
  const startup = sidecarStartupPromises.get(projectRoot);
  if (startup) await startup;
  const port = sidecarPorts.get(projectRoot);
  if (!port || !(await waitForSidecarHealth(port, SIDECAR_HEALTH_REQUEST_TIMEOUT_MS))) {
    if (port) await stopSidecar(projectRoot);
    throw new Error('sidecar_offline');
  }
  return port;
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const APP_SETTINGS_FILE = 'narrative-ide-app-settings.json';

function getSettingsPath() {
  return path.join(app.getPath('userData'), APP_SETTINGS_FILE);
}

function loadAppSettings() {
  const settingsPath = getSettingsPath();
  if (!fs.existsSync(settingsPath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
}

function saveAppSettings(partial) {
  requirePlainObject(partial, 'settings payload');
  const current = loadAppSettings() || {};
  const next = { ...current, ...partial };
  fs.mkdirSync(path.dirname(getSettingsPath()), { recursive: true });
  fs.writeFileSync(getSettingsPath(), JSON.stringify(next, null, 2), 'utf8');
  return next;
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1600,
    height: 960,
    minWidth: 1200,
    minHeight: 720,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  });

  const rendererUrl = process.env.NARRATIVE_IDE_RENDERER_URL;
  const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

  if (rendererUrl) {
    win.loadURL(rendererUrl);
  } else if (isDev) {
    win.loadURL('http://localhost:3000');
    if (!process.env.NARRATIVE_IDE_RUNTIME_SMOKE) win.webContents.openDevTools();
  } else {
    win.loadFile(path.join(__dirname, '../../dist/index.html'));
  }

  win.on('closed', () => {
    // Abort all in-flight AI streams
    for (const controller of streamControllers.values()) {
      controller.abort();
    }
    streamControllers.clear();
    runtimeEventStreams.get(win.webContents.id)?.controller.abort();
    runtimeEventStreams.delete(win.webContents.id);
    workflowEventStreams.get(win.webContents.id)?.controller.abort();
    workflowEventStreams.delete(win.webContents.id);
    // Kill per-project sidecar for this window
    const projectRoot = windowProjectMap.get(win);
    windowProjectMap.delete(win);
    senderProjectRoots.delete(win.webContents.id);
    senderSourceGrants.delete(win.webContents.id);
    if (projectRoot && !electronShutdownPromise) void stopSidecar(projectRoot);
  });
}

ipcMain.handle('dialog:pick-directory', async (event, payload = { mode: 'open' }) => {
  const mode = payload?.mode === 'create' ? 'create' : 'open';
  const result = await showOpenDialog({
    title: mode === 'create' ? 'Choose Project Parent Folder' : 'Open Narrative Project Folder',
    properties: ['openDirectory', 'createDirectory'],
  });

  const selectedPath = result.canceled ? null : await registerProjectRoot(event, result.filePaths[0], { allowProjectChild: mode === 'create' });
  return {
    canceled: result.canceled,
    path: selectedPath,
  };
});

ipcMain.handle('project:selectRoot', async (event) => {
  const result = await showOpenDialog({
    title: 'Open Narrative Project Folder',
    properties: ['openDirectory'],
  });
  return { canceled: result.canceled, path: result.canceled ? null : await registerProjectRoot(event, result.filePaths[0]) };
});

for (const operation of ['exists', 'read', 'write', 'mkdir', 'readdir', 'unlink', 'realpath', 'copy', 'rename']) {
  ipcMain.on(`projectfs:${operation}`, (event, payload) => {
    event.returnValue = handleProjectFileSync(event, operation, payload);
  });
}

ipcMain.on('crypto:sha256', (event, value) => {
  if (typeof value !== 'string' || Buffer.byteLength(value, 'utf8') > MAX_PROJECT_FILE_BYTES) {
    event.returnValue = { ok: false, error: 'Invalid SHA-256 input' };
    return;
  }
  event.returnValue = { ok: true, value: createHash('sha256').update(value, 'utf8').digest('hex') };
});

ipcMain.handle('settings:load-app', async () => loadAppSettings());
ipcMain.handle('settings:save-app', async (_event, payload = {}) => saveAppSettings(payload));
ipcMain.handle('dialog:pick-files', async (event, payload) => {
  const filters = Array.isArray(payload?.filters)
    ? payload.filters
      .filter((filter) => typeof filter?.name === 'string' && Array.isArray(filter.extensions))
      .map((filter) => ({
        name: filter.name.slice(0, 128),
        extensions: filter.extensions.filter((extension) => typeof extension === 'string' && /^[A-Za-z0-9]+$/.test(extension)).slice(0, 32),
      }))
      .filter((filter) => filter.extensions.length > 0)
    : [{ name: 'Text Files', extensions: ['txt', 'md'] }];
  const multiple = payload?.multiple !== false;
  const properties = multiple ? ['openFile', 'multiSelections'] : ['openFile'];
  const result = await showOpenDialog({
    title: 'Select Files',
    properties,
    filters,
  });
  const paths = result.canceled ? [] : await registerSourceGrants(event, result.filePaths);
  return { canceled: result.canceled, paths };
});

ipcMain.handle('settings:test-provider', async (_event, payload = {}) => testProviderConnection(payload));

// Map of active stream abort controllers
const streamControllers = new Map();

// Helper: get active AI text config from app settings
function getAITextConfig(settings) {
  const profiles = settings.providerProfiles ?? [];
  const modelProfiles = settings.modelProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  const modelProfile =
    modelProfiles.find((m) => m.id === settings.selectedModelProfileId) ?? modelProfiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: modelProfile?.model ?? 'gpt-4o-mini',
    temperature: modelProfile?.temperature ?? 0.7,
    maxTokens: modelProfile?.maxTokens ?? 2048,
  };
}

function getAIImageConfig(settings) {
  const profiles = settings.providerProfiles ?? [];
  const profile =
    profiles.find((p) => p.id === settings.selectedProviderProfileId) ?? profiles[0];
  if (!profile) throw new Error('No AI provider configured');
  return {
    endpoint: profile.endpoint,
    apiKey: profile.apiKey,
    model: profile.imageModel ?? 'dall-e-3',
    size: '1024x1024',
  };
}

function getRuntimeResumeCredentials() {
  const settings = loadAppSettings() ?? {};
  const profiles = Array.isArray(settings.providerProfiles) ? settings.providerProfiles : [];
  const models = Array.isArray(settings.modelProfiles) ? settings.modelProfiles : [];
  const provider = profiles.find((profile) => profile.id === settings.selectedProviderProfileId) ?? profiles[0];
  const model = models.find((profile) => profile.id === settings.selectedModelProfileId) ?? models[0];
  return {
    api_key: typeof provider?.apiKey === 'string' ? provider.apiKey : '',
    provider: typeof provider?.provider === 'string' ? provider.provider : undefined,
    model: typeof model?.model === 'string' ? model.model : undefined,
  };
}

// Single-turn chat
ipcMain.handle('ai:chat', async (_event, { messages }) => {
  const settings = loadAppSettings() ?? {};
  const config = getAITextConfig(settings);
  return await chatCompletion(messages, config);
});

// Image generation
ipcMain.handle('ai:generate-image', async (_event, { prompt }) => {
  const settings = loadAppSettings() ?? {};
  const config = getAIImageConfig(settings);
  return await generateImage(prompt, config);
});

// Streaming chat
ipcMain.on('ai:stream-start', async (event, { requestId, messages }) => {
  try {
    const settings = loadAppSettings() ?? {};
    const config = getAITextConfig(settings);
    const controller = new AbortController();
    streamControllers.set(requestId, controller);
    await streamCompletion(
      messages,
      config,
      (text) => event.reply(`ai:chunk:${requestId}`, text),
      controller.signal,
    );
    streamControllers.delete(requestId);
    event.reply(`ai:done:${requestId}`);
  } catch (err) {
    streamControllers.delete(requestId);
    event.reply(`ai:error:${requestId}`, err.message);
  }
});

// Save portrait image to project folder
ipcMain.handle('portrait:save', async (event, { projectRoot, characterId, imageData }) => {
  if (typeof imageData !== 'string') throw new Error('Invalid portrait payload');
  const destination = await getPortraitDestination(event, projectRoot, characterId);

  if (imageData.startsWith('https:')) {
    const buffer = await downloadPublicPortrait(imageData);
    await writePortraitDestination(destination, buffer);
  } else if (imageData.startsWith('file:')) {
    const srcPath = await consumePortraitSourceGrant(event, imageData);
    await writePortraitDestination(destination, await fsPromises.readFile(srcPath));
  } else {
    const match = imageData.match(/^data:image\/(?:png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$/);
    if (!match || match[1].length % 4 !== 0) throw new Error('Invalid portrait image data');
    const base64 = match[1];
    if (Buffer.byteLength(base64, 'base64') > MAX_PORTRAIT_BYTES) throw new Error('Portrait image is too large');
    await writePortraitDestination(destination, Buffer.from(base64, 'base64'));
  }

  return pathToFileURL(destination.filePath).href;
});

// Upload portrait from local file path by copying to project portraits folder
ipcMain.handle('portrait:upload', async (event, { projectRoot, characterId, sourcePath }) => {
  const destination = await getPortraitDestination(event, projectRoot, characterId);
  const source = await consumePortraitSourceGrant(event, sourcePath);
  await writePortraitDestination(destination, await fsPromises.readFile(source));
  return pathToFileURL(destination.filePath).href;
});

ipcMain.on('ai:stream-cancel', (_event, { requestId }) => {
  streamControllers.get(requestId)?.abort();
  streamControllers.delete(requestId);
});

// --- DB IPC handlers ---

// Open/migrate DB when project opens
ipcMain.handle('db:open', async (event, { projectRoot, projectJson }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  const db = openDb(projectRoot);
  if (projectJson) await migrateFromJson(projectRoot, projectJson);
  // Suppress unused variable warning — db used internally via openDbs map
  void db;
  return { ok: true };
});

// Close DB when project closes
ipcMain.handle('db:close', async (event, { projectRoot }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  closeDb(projectRoot);
  return { ok: true };
});

// Upsert entity
ipcMain.handle('db:upsert', async (event, { projectRoot, table, id, data }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (!ALLOWED_TABLES.has(table)) throw new Error('Invalid table');
  requireIdentifier(id, 'entity id');
  const db = openDb(projectRoot);
  upsertEntity(db, table, id, data);
  return { ok: true };
});

// Get all entities from a table
ipcMain.handle('db:getAll', async (event, { projectRoot, table }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (!ALLOWED_TABLES.has(table)) throw new Error('Invalid table');
  const db = openDb(projectRoot);
  return getAllEntities(db, table);
});

// Delete entity
ipcMain.handle('db:delete', async (event, { projectRoot, table, id }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (!ALLOWED_TABLES.has(table)) throw new Error('Invalid table');
  requireIdentifier(id, 'entity id');
  const db = openDb(projectRoot);
  deleteEntity(db, table, id);
  return { ok: true };
});

// Index entity for FTS
ipcMain.handle('db:indexEntity', async (event, { projectRoot, entityType, entityId, title, content }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  requireIdentifier(entityType, 'entity type');
  requireIdentifier(entityId, 'entity id');
  const db = openDb(projectRoot);
  indexEntity(db, entityType, entityId, title, content);
  return { ok: true };
});

// Full-text search
ipcMain.handle('db:search', async (event, { projectRoot, query }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (typeof query !== 'string' || query.length > 512) throw new Error('Invalid search query');
  const db = openDb(projectRoot);
  return searchEntities(db, query);
});

// ── Sidecar IPC handlers ──────────────────────────────────────────────────────

// Spawn sidecar for a project (called when project opens)
ipcMain.handle('sidecar:spawn', async (event, { projectRoot }) => {
  try {
    projectRoot = await requireProjectRoot(event, projectRoot);
    const port = await spawnSidecar(projectRoot);
    return { ok: true, port };
  } catch (err) {
    return { ok: false, error: err.message };
  }
});

// Poll workflow lock status (UI polls every 2s)
ipcMain.handle('workflow:status', async (event, { projectRoot }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  try {
    const port = await getReadySidecarPort(projectRoot);
    const res = await fetchWithTimeout(`http://127.0.0.1:${port}/workflow/status`);
    return await res.json();
  } catch {
    return { status: 'offline', workflowId: null, progress: 0 };
  }
});

// Force-clear a stale workflow.lock file
ipcMain.handle('workflow:force-clear', async (event, { projectRoot }) => {
  projectRoot = await requireProjectRoot(event, projectRoot);
  const lockPath = path.join(projectRoot, 'workflow.lock');
  if (fs.existsSync(lockPath)) {
    try { fs.unlinkSync(lockPath); } catch (err) {
      return { ok: false, error: err.message };
    }
  }
  return { ok: true };
});

// SSE bridge: subscribe to sidecar stream, forward events to renderer
ipcMain.on('workflow:stream-subscribe', async (event, { projectRoot }) => {
  try {
    projectRoot = await requireProjectRoot(event, projectRoot);
    const port = await getReadySidecarPort(projectRoot);
    workflowEventStreams.get(event.sender.id)?.controller.abort();
    const controller = new AbortController();
    workflowEventStreams.set(event.sender.id, { controller });
    const res = await fetch(`http://127.0.0.1:${port}/workflow/stream`, { signal: controller.signal });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    const read = async () => {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        // Parse SSE lines and forward W3 progress events separately
        for (const line of text.split('\n')) {
          if (!line.startsWith('data:')) continue;
          try {
            const data = JSON.parse(line.slice(5).trim());
            if (data.workflow_id === 'W3') event.reply('w3:progress', data);
          } catch { /* non-JSON SSE line */ }
        }
        event.reply('workflow:stream-event', text);
      }
    };
    read().catch(() => {/* stream ended */}).finally(() => {
      if (workflowEventStreams.get(event.sender.id)?.controller === controller) workflowEventStreams.delete(event.sender.id);
    });
  } catch { /* sidecar offline */ }
});

// ── Generic sidecar HTTP proxy ────────────────────────────────────────────────

async function proxyToSidecar(event, projectRoot, path, method = 'GET', body = null) {
  projectRoot = await requireProjectRoot(event, projectRoot);
  if (process.env.NARRATIVE_IDE_RUNTIME_SMOKE) {
    return { status: 'runtime-smoke', projectRoot, path, method, body };
  }
  const port = await getReadySidecarPort(projectRoot);
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`http://127.0.0.1:${port}${path}`, opts);
  return res.json();
}

// ── W3 Writing Assistant IPC handlers ─────────────────────────────────────────

ipcMain.handle('w3:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w3/start', 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w3:select', async (event, { projectRoot, sessionId, selectedOption }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/workflow/w3/select', 'POST', {
      session_id: sessionId,
      selected_option: selectedOption,
    });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w3:status', async (event, { projectRoot }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/workflow/w3/status', 'GET');
  } catch {
    return { status: 'offline', progress: 0, workflow_id: null };
  }
});

// ── W1 Import IPC handlers ─────────────────────────────────────────────────

ipcMain.handle('w1:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w1/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w1:cancel', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w1/cancel', 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w1:status', async (event, { projectRoot, session_id }) => {
  try {
    const qs = session_id ? `?session_id=${encodeURIComponent(session_id)}` : '';
    return await proxyToSidecar(event, projectRoot, `/workflow/w1/status${qs}`, 'GET');
  } catch {
    return { status: 'offline', progress: 0, errors: [], completed_chunks: 0, total_chunks: 0 };
  }
});

ipcMain.handle('w1:console', async (event, { projectRoot, session_id, after = 0, activity_after = 0 }) => {
  try {
    const qs = `?session_id=${encodeURIComponent(session_id ?? '')}&after=${encodeURIComponent(after)}&activity_after=${encodeURIComponent(activity_after)}`;
    return await proxyToSidecar(event, projectRoot, `/workflow/w1/console${qs}`, 'GET');
  } catch {
    return { entries: [], activity_entries: [], paused: false, breakpoint_chunk: null };
  }
});

ipcMain.handle('w1:set_breakpoint', async (event, { projectRoot, session_id, chunk_id }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/workflow/w1/set_breakpoint', 'POST', { session_id, chunk_id: chunk_id ?? null });
  } catch {
    return { ok: false };
  }
});

ipcMain.handle('w1:resume', async (event, { projectRoot, session_id }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/workflow/w1/resume', 'POST', { session_id });
  } catch {
    return { ok: false };
  }
});

ipcMain.handle('w1:rewind', async (event, { projectRoot, session_id, to_chunk_id }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/workflow/w1/rewind', 'POST', { session_id, to_chunk_id });
  } catch {
    return { ok: false };
  }
});

// ── Durable runtime recovery IPC handlers ───────────────────────────────────
// These routes are intentionally project-root scoped. The runtime contract is
// optional during rollout, so unsupported/offline sidecars degrade to an empty
// inventory instead of blocking the legacy W1 import controls.
async function runtimeProxy(event, projectRoot, route, method = 'GET', body = null) {
  const root = await requireProjectRoot(event, projectRoot);
  try {
    const port = await getReadySidecarPort(root);
    const options = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) options.body = JSON.stringify({ project_path: root, ...body });
    const response = await fetch(`http://127.0.0.1:${port}${route}`, options);
    const payload = await response.json().catch(() => ({}));
    return response.ok ? payload : { ...payload, error: payload?.detail || `runtime_http_${response.status}` };
  } catch {
    return { error: 'sidecar_offline' };
  }
}

function sendRuntimeStreamMessage(sender, channel, payload) {
  if (!sender.isDestroyed()) sender.send(channel, payload);
}

function normalizeRuntimeStreamEvent(value, sseEventType, sseId) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('runtime_sse_invalid_event');
  const sequence = Number(value.sequence ?? sseId);
  if (!Number.isSafeInteger(sequence) || sequence <= 0) throw new Error('runtime_sse_invalid_sequence');
  if (typeof value.event_id !== 'string' || !value.event_id) throw new Error('runtime_sse_invalid_event_id');
  const eventType = typeof value.event_type === 'string' && value.event_type ? value.event_type : sseEventType;
  if (typeof eventType !== 'string' || !eventType) throw new Error('runtime_sse_invalid_event_type');
  const createdAt = typeof value.created_at === 'string'
    ? value.created_at
    : Number.isFinite(Number(value.created_at))
      ? new Date(Number(value.created_at) * 1000).toISOString()
      : undefined;
  return {
    event_id: value.event_id,
    sequence,
    event_type: eventType,
    payload: value.payload && typeof value.payload === 'object' && !Array.isArray(value.payload) ? value.payload : {},
    ...(createdAt ? { created_at: createdAt } : {}),
  };
}

function parseRuntimeSseFrame(frame) {
  let id = '';
  let eventType = '';
  const data = [];
  for (const line of frame.split('\n')) {
    if (!line || line.startsWith(':')) continue;
    const separator = line.indexOf(':');
    const field = separator < 0 ? line : line.slice(0, separator);
    const value = separator < 0 ? '' : line.slice(separator + 1).replace(/^ /, '');
    if (field === 'id') id = value;
    if (field === 'event') eventType = value;
    if (field === 'data') data.push(value);
  }
  if (data.length === 0) return null;
  return normalizeRuntimeStreamEvent(JSON.parse(data.join('\n')), eventType, id);
}

async function consumeRuntimeEventStream(sender, subscription) {
  const { projectRoot, attemptId, subscriptionId, afterSequence, controller } = subscription;
  const port = await getReadySidecarPort(projectRoot);
  const query = new URLSearchParams({ attempt_id: attemptId, afterSequence: String(afterSequence) });
  const response = await fetch(`http://127.0.0.1:${port}/workflow/stream?${query}`, {
    headers: { Accept: 'text/event-stream', 'Last-Event-ID': String(afterSequence) },
    signal: controller.signal,
  });
  if (!response.ok || !response.body) throw new Error(`runtime_sse_http_${response.status}`);
  sendRuntimeStreamMessage(sender, 'runtime:event-stream-status', { subscription_id: subscriptionId, attempt_id: attemptId, status: 'open' });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n');
    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const event = parseRuntimeSseFrame(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      if (event) sendRuntimeStreamMessage(sender, 'runtime:event', { subscription_id: subscriptionId, attempt_id: attemptId, event });
      boundary = buffer.indexOf('\n\n');
    }
    if (done) break;
  }
  if (!controller.signal.aborted) {
    sendRuntimeStreamMessage(sender, 'runtime:event-stream-status', { subscription_id: subscriptionId, attempt_id: attemptId, status: 'closed', retryable: true });
  }
}

ipcMain.handle('runtime:event-stream-subscribe', async (event, { projectRoot, attempt_id, after_sequence = 0, subscription_id }) => {
  const root = await requireProjectRoot(event, projectRoot);
  const attemptId = requireIdentifier(attempt_id, 'attempt_id');
  const subscriptionId = requireIdentifier(subscription_id, 'subscription_id');
  const afterSequence = Number.isSafeInteger(after_sequence) && after_sequence >= 0 ? after_sequence : 0;
  runtimeEventStreams.get(event.sender.id)?.controller.abort();
  const subscription = { projectRoot: root, attemptId, subscriptionId, afterSequence, controller: new AbortController() };
  runtimeEventStreams.set(event.sender.id, subscription);
  void consumeRuntimeEventStream(event.sender, subscription).catch((error) => {
    if (!subscription.controller.signal.aborted) {
      sendRuntimeStreamMessage(event.sender, 'runtime:event-stream-status', { subscription_id: subscriptionId, attempt_id: attemptId, status: 'error', retryable: true, error: error instanceof Error ? error.message : 'runtime_sse_failed' });
    }
  }).finally(() => {
    if (runtimeEventStreams.get(event.sender.id)?.subscriptionId === subscriptionId) runtimeEventStreams.delete(event.sender.id);
  });
  return { ok: true, subscription_id: subscriptionId };
});

ipcMain.handle('runtime:event-stream-unsubscribe', async (event, { subscription_id }) => {
  const subscription = runtimeEventStreams.get(event.sender.id);
  if (subscription && (!subscription_id || subscription.subscriptionId === subscription_id)) {
    subscription.controller.abort();
    runtimeEventStreams.delete(event.sender.id);
  }
  return { ok: true };
});

ipcMain.handle('runtime:recoverable', async (event, { projectRoot }) => {
  const root = await requireProjectRoot(event, projectRoot);
  return runtimeProxy(event, root, `/runtime/runs/recoverable?project_path=${encodeURIComponent(root)}`);
});
ipcMain.handle('runtime:run', async (event, { projectRoot, lineage_id }) => {
  const root = await requireProjectRoot(event, projectRoot);
  return runtimeProxy(event, root, `/runtime/runs/${encodeURIComponent(lineage_id)}?project_path=${encodeURIComponent(root)}`);
});
ipcMain.handle('runtime:events', async (event, { projectRoot, attempt_id, after_sequence = 0 }) => {
  const root = await requireProjectRoot(event, projectRoot);
  return runtimeProxy(event, root, `/runtime/runs/${encodeURIComponent(attempt_id)}/events?afterSequence=${encodeURIComponent(after_sequence)}&project_path=${encodeURIComponent(root)}`);
});
ipcMain.handle('runtime:checkpoints', async (event, { projectRoot, attempt_id }) => {
  const root = await requireProjectRoot(event, projectRoot);
  return runtimeProxy(event, root, `/runtime/runs/${encodeURIComponent(attempt_id)}/checkpoints?project_path=${encodeURIComponent(root)}`);
});
for (const action of ['pause', 'cancel']) {
  ipcMain.handle(`runtime:${action}`, async (event, { projectRoot, attempt_id }) =>
    runtimeProxy(event, projectRoot, `/runtime/runs/${encodeURIComponent(attempt_id)}/${action}`, 'POST'),
  );
}
ipcMain.handle('runtime:resume', async (event, { projectRoot, attempt_id }) =>
  runtimeProxy(event, projectRoot, `/runtime/runs/${encodeURIComponent(attempt_id)}/resume`, 'POST', getRuntimeResumeCredentials()),
);
ipcMain.handle('runtime:fork', async (event, { projectRoot, attempt_id, checkpoint_id, decision_id }) =>
  runtimeProxy(event, projectRoot, `/runtime/runs/${encodeURIComponent(attempt_id)}/fork`, 'POST', { checkpoint_id, decision_id }),
);
ipcMain.handle('runtime:decision', async (event, { projectRoot, decision_key, attempt_id, decision }) =>
  runtimeProxy(event, projectRoot, `/runtime/decisions/${encodeURIComponent(decision_key)}`, 'POST', { attempt_id, decision }),
);

ipcMain.handle('prompts:list', async (event, { projectRoot }) => {
  try {
    return await proxyToSidecar(event, projectRoot, '/prompts/list', 'GET');
  } catch {
    return {};
  }
});

// ── W2 Manuscript Sync IPC handlers ────────────────────────────────────────

ipcMain.handle('w2:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w2/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w2:status', async (event, { projectRoot, session_id }) => {
  try {
    return await proxyToSidecar(event, projectRoot, `/workflow/w2/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', progress: 0, errors: [err.message], proposals_count: 0 };
  }
});

// ── W4 Consistency Check IPC handlers ──────────────────────────────────────

ipcMain.handle('w4:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w4/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w4:status', async (event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(event, projectRoot, `/workflow/w4/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W5 Simulation Engine IPC handlers ──────────────────────────────────────

ipcMain.handle('w5:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w5/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w5:status', async (event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(event, projectRoot, `/workflow/w5/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W6 Beta Reader IPC handlers ─────────────────────────────────────────────

ipcMain.handle('w6:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/workflow/w6/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('w6:status', async (event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(event, projectRoot, `/workflow/w6/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── W7 Metadata Ingestion IPC handlers ─────────────────────────────────────

ipcMain.handle('metadata:ingest', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/metadata/ingest', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('metadata:status', async (event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(event, projectRoot, `/metadata/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

// ── Orchestrator IPC handlers ───────────────────────────────────────────────

ipcMain.handle('orchestrator:start', async (event, payload) => {
  try {
    const { projectRoot, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, '/orchestrator/start', 'POST', { project_path: projectRoot, ...rest });
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:status', async (event, payload) => {
  try {
    const { projectRoot, session_id } = payload;
    return await proxyToSidecar(event, projectRoot, `/orchestrator/status?session_id=${encodeURIComponent(session_id ?? '')}`, 'GET');
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:grant', async (event, payload) => {
  try {
    const { projectRoot, stepId, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, `/orchestrator/permission/${stepId}/grant`, 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

ipcMain.handle('orchestrator:deny', async (event, payload) => {
  try {
    const { projectRoot, stepId, ...rest } = payload;
    return await proxyToSidecar(event, projectRoot, `/orchestrator/permission/${stepId}/deny`, 'POST', rest);
  } catch (err) {
    return { status: 'error', error: err.message };
  }
});

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (!electronShutdownPromise && !electronShutdownComplete && BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (!electronShutdownPromise && !electronShutdownComplete && process.platform !== 'darwin') {
    app.quit();
  }
});

let electronShutdownPromise = null;
let electronShutdownComplete = false;

function writeSmokeLifecycle(event) {
  if (!process.env.NARRATIVE_IDE_RUNTIME_SMOKE) return;
  const handles = typeof process._getActiveHandles === 'function'
    ? process._getActiveHandles().map((handle) => handle?.constructor?.name ?? typeof handle).sort()
    : [];
  const summary = {
    event,
    pid: process.pid,
    windows: BrowserWindow.getAllWindows().length,
    sidecars: sidecarProcesses.size,
    startupPromises: sidecarStartupPromises.size,
    shutdownPromises: sidecarShutdownPromises.size,
    aiStreams: streamControllers.size,
    runtimeStreams: runtimeEventStreams.size,
    workflowStreams: workflowEventStreams.size,
    handles,
  };
  try {
    fs.appendFileSync(path.join(app.getPath('userData'), 'electron-lifecycle-smoke.jsonl'), `${JSON.stringify(summary)}\n`);
  } catch { /* diagnostics must never block shutdown */ }
}

function abortActiveStreams() {
  for (const controller of streamControllers.values()) controller.abort();
  streamControllers.clear();
  for (const { controller } of runtimeEventStreams.values()) controller.abort();
  runtimeEventStreams.clear();
  for (const { controller } of workflowEventStreams.values()) controller.abort();
  workflowEventStreams.clear();
}

async function shutdownElectronResources() {
  if (electronShutdownPromise) return electronShutdownPromise;
  electronShutdownPromise = (async () => {
    abortActiveStreams();
    closeAllDbs();
    await stopAllSidecars();
  })();
  return electronShutdownPromise;
}

app.on('before-quit', (event) => {
  writeSmokeLifecycle('before-quit');
  if (electronShutdownComplete) return;
  event.preventDefault();
  void shutdownElectronResources()
    .catch((error) => console.error('[electron] sidecar shutdown failed', error))
    .finally(() => {
      electronShutdownComplete = true;
      writeSmokeLifecycle('shutdown-complete');
      // Leave the intercepted before-quit callback before the final native
      // exit; Electron defers termination when exit is invoked in that stack.
      setImmediate(() => {
        writeSmokeLifecycle('final-exit');
        for (const window of BrowserWindow.getAllWindows()) window.destroy();
        app.removeAllListeners('before-quit');
        if (typeof process.reallyExit === 'function') process.reallyExit(0);
        else process.exit(0);
      });
    });
});

app.on('will-quit', () => writeSmokeLifecycle('will-quit'));
