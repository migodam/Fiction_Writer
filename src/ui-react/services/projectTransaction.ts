export type TransactionDurability = 'power-loss' | 'best-effort';

/**
 * `power-loss` is only valid for an implementation that fsyncs both the file
 * contents and each affected directory. Browser fixtures deliberately use the
 * weaker fallback so tests cannot accidentally claim physical durability.
 */
export type TransactionFileSystem = Pick<typeof import('fs'), 'existsSync' | 'readFileSync' | 'writeFileSync' | 'mkdirSync' | 'renameSync' | 'unlinkSync' | 'readdirSync'> & {
  durability?: TransactionDurability;
  fsyncDirectorySync?: (directory: string) => void;
};

export type ProjectTransactionReceipt = {
  id: string;
  journalPath: string;
  backupPath: string;
  durability: TransactionDurability;
};

export type ProjectTransactionOperation =
  | { relativePath: string; postimage: string; delete?: never }
  | { relativePath: string; delete: true; postimage?: never };

export type ProjectTransactionCrashPoint =
  | 'before-commit-intent'
  | 'before-first-rename'
  | 'mid-rename'
  | 'after-last-rename-before-commit';
export type ProjectTransactionPhase = 'prepared' | 'commit-intent' | 'target-applied' | 'committed' | 'rolled-back';
export type ProjectTransactionOptions = {
  /** Test-only deterministic failpoint. Production callers must leave this unset. */
  crashAt?: ProjectTransactionCrashPoint;
  /** Test-only hook used by a child process to terminate at a durable boundary. */
  onPhase?: (phase: ProjectTransactionPhase, targetIndex?: number) => void;
};

type Image = { present: boolean; sha256: string; stage: string | null };
type PreparedTransaction = {
  version: 1 | 2 | 3;
  id: string;
  targets: Array<{ relativePath: string; intent?: 'write' | 'delete'; preimage: Image; postimage: Image }>;
};

const join = (...parts: string[]) => parts.filter(Boolean).join('/').replace(/\\/g, '/').replace(/\/+/g, '/');
export const sha256Text = async (value: string): Promise<string> => {
  if (!globalThis.crypto?.subtle) throw new Error('Project transactions require a SHA-256 implementation.');
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
};

const isRelativePath = (value: string) => Boolean(value)
  && !value.startsWith('/')
  && !value.includes('\\')
  && value.split('/').every((segment) => segment && segment !== '.' && segment !== '..');

const readImage = (fs: TransactionFileSystem, targetPath: string): { present: boolean; content: string | null } =>
  fs.existsSync(targetPath)
    ? { present: true, content: fs.readFileSync(targetPath, 'utf8') as string }
    : { present: false, content: null };

const transactionDurability = (fs: TransactionFileSystem): TransactionDurability =>
  fs.durability === 'power-loss' ? 'power-loss' : 'best-effort';

const syncDirectory = (fs: TransactionFileSystem, directory: string) => {
  if (fs.fsyncDirectorySync) {
    fs.fsyncDirectorySync(directory);
    return;
  }
  if (transactionDurability(fs) === 'power-loss') {
    throw new Error(`Power-loss durable transaction filesystem is missing directory fsync for ${directory}.`);
  }
};

const parentDirectory = (targetPath: string) => targetPath.split('/').slice(0, -1).join('/') || '/';

const ensureDirectory = (fs: TransactionFileSystem, directory: string) => {
  fs.mkdirSync(directory, { recursive: true });
  syncDirectory(fs, directory);
};

const writeJournalFile = (fs: TransactionFileSystem, targetPath: string, content: string) => {
  ensureDirectory(fs, parentDirectory(targetPath));
  fs.writeFileSync(targetPath, content, 'utf8');
  // Electron's named bridge writes through a temp file, fsyncs it, renames it,
  // and fsyncs this directory. The fallback is intentionally best-effort.
  syncDirectory(fs, parentDirectory(targetPath));
};

const renameJournalFile = (fs: TransactionFileSystem, sourcePath: string, targetPath: string) => {
  ensureDirectory(fs, parentDirectory(targetPath));
  fs.renameSync(sourcePath, targetPath);
  syncDirectory(fs, parentDirectory(targetPath));
  if (parentDirectory(sourcePath) !== parentDirectory(targetPath)) syncDirectory(fs, parentDirectory(sourcePath));
};

const unlinkJournalFile = (fs: TransactionFileSystem, targetPath: string) => {
  if (!fs.existsSync(targetPath)) return;
  fs.unlinkSync(targetPath);
  syncDirectory(fs, parentDirectory(targetPath));
};

const validImage = async (fs: TransactionFileSystem, transactionDirectory: string, image: Image, targetPath: string) => {
  const actual = readImage(fs, targetPath);
  if (actual.present !== image.present) return false;
  if (!actual.present) return true;
  if (!image.stage || !fs.existsSync(join(transactionDirectory, image.stage))) return false;
  const staged = fs.readFileSync(join(transactionDirectory, image.stage), 'utf8') as string;
  return (await sha256Text(actual.content || '')) === image.sha256
    && (await sha256Text(staged)) === image.sha256
    && actual.content === staged;
};

const restoreImage = async (fs: TransactionFileSystem, transactionDirectory: string, image: Image, targetPath: string) => {
  if (!image.present) {
    unlinkJournalFile(fs, targetPath);
    return;
  }
  if (!image.stage) throw new Error(`Transaction preimage is missing for ${targetPath}.`);
  const stagedPath = join(transactionDirectory, image.stage);
  if (!fs.existsSync(stagedPath)) throw new Error(`Transaction preimage stage is missing for ${targetPath}.`);
  const staged = fs.readFileSync(stagedPath, 'utf8') as string;
  if ((await sha256Text(staged)) !== image.sha256) throw new Error(`Transaction preimage hash is invalid for ${targetPath}.`);
  const rollbackPath = join(transactionDirectory, 'rollback', image.sha256);
  ensureDirectory(fs, join(transactionDirectory, 'rollback'));
  writeJournalFile(fs, rollbackPath, staged);
  renameJournalFile(fs, rollbackPath, targetPath);
};

const applyImage = async (fs: TransactionFileSystem, transactionDirectory: string, image: Image, targetPath: string) => {
  if (!image.present) {
    unlinkJournalFile(fs, targetPath);
    return;
  }
  if (!image.stage) throw new Error(`Transaction postimage is missing for ${targetPath}.`);
  const stagedPath = join(transactionDirectory, image.stage);
  if (!fs.existsSync(stagedPath)) throw new Error(`Transaction postimage stage is missing for ${targetPath}.`);
  const staged = fs.readFileSync(stagedPath, 'utf8') as string;
  if ((await sha256Text(staged)) !== image.sha256) throw new Error(`Transaction postimage hash is invalid for ${targetPath}.`);
  const applyPath = join(transactionDirectory, 'apply', image.sha256);
  ensureDirectory(fs, join(transactionDirectory, 'apply'));
  writeJournalFile(fs, applyPath, staged);
  renameJournalFile(fs, applyPath, targetPath);
};

const phase = (options: ProjectTransactionOptions, value: ProjectTransactionPhase, targetIndex?: number) => {
  options.onPhase?.(value, targetIndex);
};

const normalizedOptions = (value?: ProjectTransactionCrashPoint | ProjectTransactionOptions): ProjectTransactionOptions =>
  typeof value === 'string' ? { crashAt: value } : value || {};

export const commitProjectTransaction = async (
  fs: TransactionFileSystem,
  projectRoot: string,
  id: string,
  operations: ProjectTransactionOperation[],
  optionsOrCrashAt?: ProjectTransactionCrashPoint | ProjectTransactionOptions,
): Promise<ProjectTransactionReceipt> => {
  const options = normalizedOptions(optionsOrCrashAt);
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$/.test(id)) throw new Error('Invalid transaction id.');
  const ordered = [...operations].sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  if (!ordered.length || ordered.some(({ relativePath }) => !isRelativePath(relativePath)) || new Set(ordered.map(({ relativePath }) => relativePath)).size !== ordered.length) {
    throw new Error('Transaction targets must be unique project-relative paths.');
  }
  const transactionsDirectory = join(projectRoot, 'system', 'transactions');
  let transactionId = id;
  let transactionDirectory = join(transactionsDirectory, transactionId);
  let retry = 0;
  while (fs.existsSync(transactionDirectory)) {
    retry += 1;
    transactionId = `${id}-${retry}`;
    transactionDirectory = join(transactionsDirectory, transactionId);
  }
  const preparedPath = join(transactionDirectory, 'prepared.json');
  const committedPath = join(transactionDirectory, 'committed.json');
  ensureDirectory(fs, transactionDirectory);

  const targets: PreparedTransaction['targets'] = [];
  for (const [index, operation] of ordered.entries()) {
    const { relativePath } = operation;
    const deleting = operation.delete === true;
    const postimage = deleting ? null : operation.postimage;
    const targetPath = join(projectRoot, relativePath);
    const preimage = readImage(fs, targetPath);
    const preStage = preimage.present ? `pre/${index}.txt` : null;
    const postStage = postimage === null ? null : `post/${index}.txt`;
    if (preStage) {
      ensureDirectory(fs, join(transactionDirectory, 'pre'));
      writeJournalFile(fs, join(transactionDirectory, preStage), preimage.content || '');
    }
    if (postStage) {
      ensureDirectory(fs, join(transactionDirectory, 'post'));
      writeJournalFile(fs, join(transactionDirectory, postStage), postimage as string);
    }
    targets.push({
      relativePath,
      intent: deleting ? 'delete' : 'write',
      preimage: { present: preimage.present, sha256: preimage.present ? await sha256Text(preimage.content || '') : '', stage: preStage },
      postimage: { present: postimage !== null, sha256: postimage !== null ? await sha256Text(postimage) : '', stage: postStage },
    });
  }
  const prepared: PreparedTransaction = { version: 3, id: transactionId, targets };
  writeJournalFile(fs, join(transactionDirectory, 'manifest.json'), JSON.stringify(prepared));
  writeJournalFile(fs, preparedPath, JSON.stringify({ id: transactionId, state: 'prepared', version: 3 }));
  phase(options, 'prepared');
  if (options.crashAt === 'before-commit-intent') throw new Error('Crash injection: before commit intent');

  // This durable decision is the only point at which recovery changes from
  // rollback to completion. It prevents a mixed package after a power loss.
  const intentPath = join(transactionDirectory, 'commit-intent.json');
  writeJournalFile(fs, intentPath, JSON.stringify({ id: transactionId, state: 'commit-intent', version: 3 }));
  phase(options, 'commit-intent');
  if (options.crashAt === 'before-first-rename') throw new Error('Crash injection: before first rename');

  for (let index = 0; index < targets.length; index += 1) {
    const target = targets[index];
    const targetPath = join(projectRoot, target.relativePath);
    await applyImage(fs, transactionDirectory, target.postimage, targetPath);
    phase(options, 'target-applied', index);
    if (options.crashAt === 'mid-rename' && index === 0 && targets.length > 1) throw new Error('Crash injection: mid rename');
  }
  if (options.crashAt === 'after-last-rename-before-commit') throw new Error('Crash injection: after last rename');
  writeJournalFile(fs, committedPath, JSON.stringify({ id: transactionId, state: 'committed', version: 3 }));
  phase(options, 'committed');
  return {
    id: transactionId,
    journalPath: `system/transactions/${transactionId}/manifest.json`,
    backupPath: `system/transactions/${transactionId}/pre`,
    durability: transactionDurability(fs),
  };
};

export const recoverProjectTransactions = async (fs: TransactionFileSystem, projectRoot: string): Promise<void> => {
  const transactionsDirectory = join(projectRoot, 'system', 'transactions');
  if (!fs.existsSync(transactionsDirectory)) return;
  for (const id of fs.readdirSync(transactionsDirectory).sort()) {
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$/.test(id)) continue;
    const transactionDirectory = join(transactionsDirectory, id);
    const preparedPath = join(transactionDirectory, 'prepared.json');
    const committedPath = join(transactionDirectory, 'committed.json');
    const manifestPath = join(transactionDirectory, 'manifest.json');
    if (!fs.existsSync(preparedPath) || !fs.existsSync(manifestPath)) continue;
    const prepared = JSON.parse(fs.readFileSync(manifestPath, 'utf8') as string) as PreparedTransaction;
    if (
      (prepared.version !== 1 && prepared.version !== 2 && prepared.version !== 3)
      || prepared.id !== id
      || !Array.isArray(prepared.targets)
      || prepared.targets.some((target) => !isRelativePath(target.relativePath)
        || (prepared.version === 2 && target.intent !== 'write' && target.intent !== 'delete')
        || (target.intent === 'delete' && target.postimage.present))
    ) {
      throw new Error(`Invalid prepared project transaction ${id}.`);
    }
    const intentPath = join(transactionDirectory, 'commit-intent.json');
    const terminalState = fs.existsSync(committedPath)
      ? (JSON.parse(fs.readFileSync(committedPath, 'utf8') as string) as { id?: unknown; state?: unknown }).state
      : null;
    if (terminalState !== null && (terminalState !== 'committed' && terminalState !== 'rolled_back')) {
      throw new Error(`Invalid terminal project transaction marker ${id}.`);
    }
    const shouldComplete = terminalState === 'committed'
      || (terminalState === null && prepared.version >= 3 && fs.existsSync(intentPath));
    if (shouldComplete) {
      for (const target of prepared.targets) {
        const targetPath = join(projectRoot, target.relativePath);
        if (!(await validImage(fs, transactionDirectory, target.postimage, targetPath))) {
          await applyImage(fs, transactionDirectory, target.postimage, targetPath);
        }
      }
      const complete = (await Promise.all(prepared.targets.map((target) => validImage(fs, transactionDirectory, target.postimage, join(projectRoot, target.relativePath))))).every(Boolean);
      if (!complete) throw new Error(`Could not finish committed project transaction ${id}.`);
      writeJournalFile(fs, committedPath, JSON.stringify({ id, state: 'committed', recovered: true, version: prepared.version }));
      continue;
    }
    if (terminalState === 'rolled_back') {
      const rolledBack = (await Promise.all(prepared.targets.map((target) => validImage(fs, transactionDirectory, target.preimage, join(projectRoot, target.relativePath))))).every(Boolean);
      if (!rolledBack) {
        for (const target of [...prepared.targets].sort((a, b) => a.relativePath.localeCompare(b.relativePath))) {
          await restoreImage(fs, transactionDirectory, target.preimage, join(projectRoot, target.relativePath));
        }
      }
      continue;
    }
    // Version 1/2 had no commit decision. Preserve their historical behavior:
    // a completely applied transaction is committed; otherwise it rolls back.
    const complete = (await Promise.all(prepared.targets.map((target) => validImage(fs, transactionDirectory, target.postimage, join(projectRoot, target.relativePath))))).every(Boolean);
    if (complete) {
      writeJournalFile(fs, committedPath, JSON.stringify({ id, state: 'committed', recovered: true, version: prepared.version }));
      continue;
    }
    for (const target of [...prepared.targets].sort((a, b) => a.relativePath.localeCompare(b.relativePath))) {
      await restoreImage(fs, transactionDirectory, target.preimage, join(projectRoot, target.relativePath));
    }
    writeJournalFile(fs, committedPath, JSON.stringify({ id, state: 'rolled_back', recovered: true, version: prepared.version }));
  }
};

/** Backward-compatible single-file facade used by the legacy artifact migration. */
export const replaceArtifactWithJournal = async (
  fs: TransactionFileSystem,
  directory: string,
  targetPath: string,
  replacement: string,
  id: string,
): Promise<ProjectTransactionReceipt> => {
  const slash = directory.lastIndexOf('/transactions');
  const projectRoot = slash > 0 ? directory.slice(0, slash) : directory.replace(/\/transactions$/, '');
  const relativePath = targetPath.startsWith(`${projectRoot}/`) ? targetPath.slice(projectRoot.length + 1) : targetPath.split('/').filter(Boolean).slice(-1)[0];
  return await commitProjectTransaction(fs, projectRoot, id, [{ relativePath, postimage: replacement }]);
};
