export type TransactionFileSystem = Pick<typeof import('fs'), 'existsSync' | 'readFileSync' | 'writeFileSync' | 'mkdirSync' | 'renameSync' | 'unlinkSync' | 'readdirSync'>;

export type ProjectTransactionReceipt = {
  id: string;
  journalPath: string;
  backupPath: string;
};

export type ProjectTransactionOperation =
  | { relativePath: string; postimage: string; delete?: never }
  | { relativePath: string; delete: true; postimage?: never };

export type ProjectTransactionCrashPoint = 'before-first-rename' | 'mid-rename' | 'after-last-rename-before-commit';

type Image = { present: boolean; sha256: string; stage: string | null };
type PreparedTransaction = {
  version: 1 | 2;
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
    if (fs.existsSync(targetPath)) fs.unlinkSync(targetPath);
    return;
  }
  if (!image.stage) throw new Error(`Transaction preimage is missing for ${targetPath}.`);
  const stagedPath = join(transactionDirectory, image.stage);
  if (!fs.existsSync(stagedPath)) throw new Error(`Transaction preimage stage is missing for ${targetPath}.`);
  const staged = fs.readFileSync(stagedPath, 'utf8') as string;
  if ((await sha256Text(staged)) !== image.sha256) throw new Error(`Transaction preimage hash is invalid for ${targetPath}.`);
  const rollbackPath = join(transactionDirectory, 'rollback', image.sha256);
  fs.mkdirSync(join(transactionDirectory, 'rollback'), { recursive: true });
  fs.writeFileSync(rollbackPath, staged, 'utf8');
  fs.mkdirSync(targetPath.split('/').slice(0, -1).join('/'), { recursive: true });
  fs.renameSync(rollbackPath, targetPath);
};

/**
 * The synchronous project-files bridge does not expose fsync. This is therefore
 * rename plus an explicit WAL protocol, not a claim of power-loss durability.
 */
export const commitProjectTransaction = async (
  fs: TransactionFileSystem,
  projectRoot: string,
  id: string,
  operations: ProjectTransactionOperation[],
  crashAt?: ProjectTransactionCrashPoint,
): Promise<ProjectTransactionReceipt> => {
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
  fs.mkdirSync(transactionDirectory, { recursive: true });

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
      fs.mkdirSync(join(transactionDirectory, 'pre'), { recursive: true });
      fs.writeFileSync(join(transactionDirectory, preStage), preimage.content || '', 'utf8');
    }
    if (postStage) {
      fs.mkdirSync(join(transactionDirectory, 'post'), { recursive: true });
      fs.writeFileSync(join(transactionDirectory, postStage), postimage as string, 'utf8');
      fs.mkdirSync(join(transactionDirectory, 'apply'), { recursive: true });
      fs.writeFileSync(join(transactionDirectory, `apply/${index}.txt`), postimage as string, 'utf8');
    }
    targets.push({
      relativePath,
      intent: deleting ? 'delete' : 'write',
      preimage: { present: preimage.present, sha256: preimage.present ? await sha256Text(preimage.content || '') : '', stage: preStage },
      postimage: { present: postimage !== null, sha256: postimage !== null ? await sha256Text(postimage) : '', stage: postStage },
    });
  }
  const prepared: PreparedTransaction = { version: 2, id: transactionId, targets };
  fs.writeFileSync(join(transactionDirectory, 'manifest.json'), JSON.stringify(prepared), 'utf8');
  fs.writeFileSync(preparedPath, JSON.stringify({ id: transactionId, state: 'prepared' }), 'utf8');
  if (crashAt === 'before-first-rename') throw new Error('Crash injection: before first rename');

  for (let index = 0; index < targets.length; index += 1) {
    const target = targets[index];
    const targetPath = join(projectRoot, target.relativePath);
    fs.mkdirSync(targetPath.split('/').slice(0, -1).join('/'), { recursive: true });
    if (target.postimage.present) fs.renameSync(join(transactionDirectory, `apply/${index}.txt`), targetPath);
    else if (fs.existsSync(targetPath)) fs.unlinkSync(targetPath);
    if (crashAt === 'mid-rename' && index === 0 && targets.length > 1) throw new Error('Crash injection: mid rename');
  }
  if (crashAt === 'after-last-rename-before-commit') throw new Error('Crash injection: after last rename');
  fs.writeFileSync(committedPath, JSON.stringify({ id: transactionId, state: 'committed' }), 'utf8');
  return { id: transactionId, journalPath: `system/transactions/${transactionId}/manifest.json`, backupPath: `system/transactions/${transactionId}/pre` };
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
    if (!fs.existsSync(preparedPath) || fs.existsSync(committedPath) || !fs.existsSync(manifestPath)) continue;
    const prepared = JSON.parse(fs.readFileSync(manifestPath, 'utf8') as string) as PreparedTransaction;
    if (
      (prepared.version !== 1 && prepared.version !== 2)
      || prepared.id !== id
      || !Array.isArray(prepared.targets)
      || prepared.targets.some((target) => !isRelativePath(target.relativePath)
        || (prepared.version === 2 && target.intent !== 'write' && target.intent !== 'delete')
        || (target.intent === 'delete' && target.postimage.present))
    ) {
      throw new Error(`Invalid prepared project transaction ${id}.`);
    }
    const complete = (await Promise.all(prepared.targets.map((target) => validImage(fs, transactionDirectory, target.postimage, join(projectRoot, target.relativePath))))).every(Boolean);
    if (complete) {
      fs.writeFileSync(committedPath, JSON.stringify({ id, state: 'committed', recovered: true }), 'utf8');
      continue;
    }
    for (const target of [...prepared.targets].sort((a, b) => a.relativePath.localeCompare(b.relativePath))) {
      await restoreImage(fs, transactionDirectory, target.preimage, join(projectRoot, target.relativePath));
    }
    fs.writeFileSync(committedPath, JSON.stringify({ id, state: 'rolled_back', recovered: true }), 'utf8');
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
