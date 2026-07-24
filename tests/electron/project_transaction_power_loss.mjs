import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, readdirSync, renameSync, rmSync, unlinkSync, writeFileSync } from 'node:fs';
import { build } from 'esbuild';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const repositoryRoot = resolve(new URL('../..', import.meta.url).pathname);
const transactionSource = join(repositoryRoot, 'src/ui-react/services/projectTransaction.ts');

const fsyncDirectorySync = (directory) => {
  const descriptor = openSync(directory, 0);
  try {
    fsyncSync(descriptor);
  } finally {
    closeSync(descriptor);
  }
};

const durableFs = {
  durability: 'power-loss',
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  renameSync,
  unlinkSync,
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
  mkdirSync(join(root, 'entities'), { recursive: true });
  writeFileSync(join(root, 'entities/a.json'), 'before-a', 'utf8');
  writeFileSync(join(root, 'entities/b.json'), 'before-b', 'utf8');
  fsyncDirectorySync(join(root, 'entities'));
};

const readSnapshot = (root) => ({
  a: readFileSync(join(root, 'entities/a.json'), 'utf8'),
  b: existsSync(join(root, 'entities/b.json')) ? readFileSync(join(root, 'entities/b.json'), 'utf8') : null,
});

const transactionIdFor = (phase, targetIndex) => `power-loss-${phase}-${targetIndex || 'none'}`;

const runCrashCase = async (compiledPath, directory, phase, targetIndex, corruptCommittedTarget = false) => {
  const root = join(directory, `project-${phase}-${targetIndex || 'none'}`);
  mkdirSync(root, { recursive: true });
  writeInitialProject(root);
  const child = spawnSync(process.execPath, [new URL(import.meta.url).pathname, 'child', compiledPath, root, phase, targetIndex ?? ''], {
    encoding: 'utf8',
    timeout: 6_000,
  });
  assert.equal(child.error, undefined, `child ${phase} should not time out: ${child.error?.message || ''}`);
  assert.equal(child.status, 97, `child ${phase} should terminate at the failpoint: ${child.stderr}`);
  if (corruptCommittedTarget) {
    writeFileSync(join(root, 'entities/a.json'), 'corrupt-after-commit', 'utf8');
    fsyncDirectorySync(join(root, 'entities'));
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
mkdirSync(scratch, { recursive: true });
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
