import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { closeSync, constants, existsSync, fsyncSync, mkdirSync as nodeMkdirSync, openSync, readFileSync, readdirSync, renameSync as nodeRenameSync, rmSync, unlinkSync as nodeUnlinkSync, writeFileSync as nodeWriteFileSync } from 'node:fs';
import { build } from 'esbuild';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const repositoryRoot = resolve(new URL('../..', import.meta.url).pathname);
const transactionSource = join(repositoryRoot, 'src/ui-react/services/projectTransaction.ts');

const fsyncDirectorySync = (directory) => {
  const descriptor = openSync(directory, constants.O_RDONLY | (constants.O_DIRECTORY || 0));
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
};

let temporaryCounter = 0;
const durableMkdirSync = (directory) => {
  if (existsSync(directory)) {
    fsyncDirectorySync(directory);
    return;
  }
  const missing = [];
  let current = directory;
  while (!existsSync(current)) {
    missing.push(current);
    const parent = dirname(current);
    if (parent === current) throw new Error(`No existing parent for ${directory}`);
    current = parent;
  }
  for (const next of missing.reverse()) {
    const parent = dirname(next);
    nodeMkdirSync(next);
    fsyncDirectorySync(next);
    fsyncDirectorySync(parent);
  }
};

const durableWriteFileSync = (target, data, encoding = 'utf8') => {
  const directory = dirname(target);
  durableMkdirSync(directory);
  const temporary = join(directory, `.${basename(target)}.${process.pid}.${Date.now()}.${temporaryCounter += 1}.tmp`);
  let descriptor;
  try {
    descriptor = openSync(temporary, constants.O_WRONLY | constants.O_CREAT | constants.O_EXCL | (constants.O_NOFOLLOW || 0), 0o600);
    nodeWriteFileSync(descriptor, data, encoding);
    fsyncSync(descriptor);
    closeSync(descriptor);
    descriptor = undefined;
    nodeRenameSync(temporary, target);
    fsyncDirectorySync(directory);
  } catch (error) {
    if (descriptor !== undefined) {
      try { closeSync(descriptor); } catch { /* best-effort test cleanup */ }
    }
    try { nodeUnlinkSync(temporary); } catch { /* best-effort test cleanup */ }
    throw error;
  }
};

const durableRenameSync = (source, target) => {
  durableMkdirSync(dirname(target));
  nodeRenameSync(source, target);
  fsyncDirectorySync(dirname(target));
  if (dirname(source) !== dirname(target)) fsyncDirectorySync(dirname(source));
};

const durableUnlinkSync = (target) => {
  nodeUnlinkSync(target);
  fsyncDirectorySync(dirname(target));
};

const durableFs = {
  durability: 'power-loss',
  existsSync,
  readFileSync,
  writeFileSync: durableWriteFileSync,
  mkdirSync: durableMkdirSync,
  renameSync: durableRenameSync,
  unlinkSync: durableUnlinkSync,
  readdirSync,
  fsyncDirectorySync,
};

const childMode = process.argv[2] === 'child';
if (childMode) {
  const [, , , compiledPath, projectRoot, exitPhase, targetIndex] = process.argv;
  const { commitProjectTransaction } = await import(pathToFileURL(compiledPath).href);
  await commitProjectTransaction(
    durableFs,
    projectRoot,
    `power-loss-${exitPhase}-${targetIndex || 'none'}`,
    [
      { relativePath: 'entities/a.json', postimage: 'after-a' },
      { relativePath: 'entities/b.json', delete: true },
    ],
    {
      onPhase: (phase, index) => {
        if (phase === exitPhase && (!targetIndex || String(index) === targetIndex)) process.exit(97);
      },
    },
  );
  process.exit(0);
}

const compileTransaction = async (directory) => {
  const outfile = join(directory, 'projectTransaction.mjs');
  await build({
    entryPoints: [transactionSource],
    outfile,
    bundle: true,
    format: 'esm',
    platform: 'node',
    target: 'node20',
    sourcemap: false,
    logLevel: 'silent',
  });
  return outfile;
};

const writeInitialProject = (root) => {
  durableFs.mkdirSync(join(root, 'entities'));
  durableFs.writeFileSync(join(root, 'entities/a.json'), 'before-a', 'utf8');
  durableFs.writeFileSync(join(root, 'entities/b.json'), 'before-b', 'utf8');
};

const readSnapshot = (root) => ({
  a: readFileSync(join(root, 'entities/a.json'), 'utf8'),
  b: existsSync(join(root, 'entities/b.json')) ? readFileSync(join(root, 'entities/b.json'), 'utf8') : null,
});

const transactionIdFor = (phase, targetIndex) => `power-loss-${phase}-${targetIndex || 'none'}`;

const runCrashCase = async (compiledPath, directory, phase, targetIndex, corruptCommittedTarget = false) => {
  const root = join(directory, `project-${phase}-${targetIndex || 'none'}`);
  durableFs.mkdirSync(root);
  writeInitialProject(root);
  assert.equal(existsSync(join(root, 'system/transactions')), false, 'crash fixture must start without the transaction directory');
  const child = spawnSync(process.execPath, [new URL(import.meta.url).pathname, 'child', compiledPath, root, phase, targetIndex ?? ''], {
    encoding: 'utf8',
    timeout: 6_000,
  });
  assert.equal(child.error, undefined, `child ${phase} should not time out: ${child.error?.message || ''}`);
  assert.equal(child.status, 97, `child ${phase} should terminate at the failpoint: ${child.stderr}`);
  if (corruptCommittedTarget) {
    durableFs.writeFileSync(join(root, 'entities/a.json'), 'corrupt-after-commit', 'utf8');
  }

  const { recoverProjectTransactions } = await import(`${pathToFileURL(compiledPath).href}?${encodeURIComponent(phase)}-${targetIndex || 'none'}`);
  await recoverProjectTransactions(durableFs, root);
  const first = readSnapshot(root);
  await recoverProjectTransactions(durableFs, root);
  const second = readSnapshot(root);
  assert.deepEqual(second, first, `${phase} recovery must be idempotent`);
  const marker = readFileSync(join(root, 'system/transactions', transactionIdFor(phase, targetIndex), 'committed.json'), 'utf8');
  return { first, marker };
};

const scratch = join(tmpdir(), `narrative-transaction-power-loss-${process.pid}-${Date.now()}`);
durableFs.mkdirSync(scratch);
try {
  const compiledPath = await compileTransaction(scratch);
  const prepared = await runCrashCase(compiledPath, scratch, 'prepared');
  assert.deepEqual(prepared.first, { a: 'before-a', b: 'before-b' });
  assert.match(prepared.marker, /rolled_back/);

  for (const [phase, index] of [['commit-intent', undefined], ['target-applied', '0']]) {
    const recovered = await runCrashCase(compiledPath, scratch, phase, index);
    assert.deepEqual(recovered.first, { a: 'after-a', b: null });
    assert.match(recovered.marker, /committed/);
  }

  const committed = await runCrashCase(compiledPath, scratch, 'committed', undefined, true);
  assert.deepEqual(committed.first, { a: 'after-a', b: null });
  assert.match(committed.marker, /committed/);

  console.log('project transaction real-filesystem crash recovery: passed');
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
