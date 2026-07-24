import { expect, test } from '@playwright/test';

type CrashPoint = 'before-first-rename' | 'mid-rename' | 'after-last-rename-before-commit';

const recoverAfterCrash = async (page: import('@playwright/test').Page, crashAt: CrashPoint) => page.evaluate(async (point) => {
  const { commitProjectTransaction, recoverProjectTransactions } = await import('/src/ui-react/services/projectTransaction.ts');
  const files = new Map<string, string>([
    ['/project/entities/a.json', 'before-a'],
    ['/project/entities/b.json', 'before-b'],
    ['/project/unrelated/keep.txt', 'keep'],
  ]);
  const directories = new Set(['/project', '/project/entities', '/project/system', '/project/system/transactions']);
  const directChildren = (directory: string) => {
    const prefix = `${directory}/`;
    return Array.from(new Set([...directories, ...files.keys()]
      .filter((path) => path.startsWith(prefix))
      .map((path) => path.slice(prefix.length).split('/')[0])
      .filter(Boolean)));
  };
  delete (globalThis as any).require;
  const fs = {
    existsSync: (path: string) => files.has(path) || directories.has(path),
    readFileSync: (path: string) => files.get(path) ?? '',
    writeFileSync: (path: string, value: string) => { files.set(path, String(value)); },
    mkdirSync: (path: string) => { directories.add(path); },
    renameSync: (from: string, to: string) => { files.set(to, files.get(from) ?? ''); files.delete(from); },
    unlinkSync: (path: string) => { files.delete(path); },
    readdirSync: (path: string) => directChildren(path),
  };
  try {
    await commitProjectTransaction(fs as any, '/project', 'package-crash-test', [
      { relativePath: 'entities/a.json', postimage: 'after-a' },
      { relativePath: 'entities/b.json', delete: true },
    ], point);
  } catch { /* Simulated process termination leaves the prepared WAL on disk. */ }
  await recoverProjectTransactions(fs as any, '/project');
  const firstRecovery = [files.get('/project/entities/a.json'), files.get('/project/entities/b.json')];
  await recoverProjectTransactions(fs as any, '/project');
  return {
    files: firstRecovery,
    repeatedRecovery: [files.get('/project/entities/a.json'), files.get('/project/entities/b.json')],
    unrelated: files.get('/project/unrelated/keep.txt'),
    marker: files.get('/project/system/transactions/package-crash-test/committed.json'),
    manifest: files.get('/project/system/transactions/package-crash-test/manifest.json'),
  };
}, crashAt);

test('completes a decided package after a browser-fallback crash before the first rename', async ({ page }) => {
  await page.goto('http://localhost:3000');
  const result = await recoverAfterCrash(page, 'before-first-rename');
  expect(result.files).toEqual(['after-a', undefined]);
  expect(result.repeatedRecovery).toEqual(result.files);
  expect(result.unrelated).toBe('keep');
  expect(result.marker).toContain('committed');
});

test('commits exact lowercase SHA-256 hashes without Node require', async ({ page }) => {
  await page.goto('http://localhost:3000');
  const result = await page.evaluate(async () => {
    const { commitProjectTransaction } = await import('/src/ui-react/services/projectTransaction.ts');
    delete (globalThis as any).require;
    const files = new Map<string, string>();
    const directories = new Set(['/project']);
    const fs = {
      existsSync: (path: string) => files.has(path) || directories.has(path),
      readFileSync: (path: string) => files.get(path) ?? '',
      writeFileSync: (path: string, value: string) => { files.set(path, String(value)); },
      mkdirSync: (path: string) => { directories.add(path); },
      renameSync: (from: string, to: string) => { files.set(to, files.get(from) ?? ''); files.delete(from); },
      unlinkSync: (path: string) => { files.delete(path); },
      readdirSync: () => [],
    };
    await commitProjectTransaction(fs as any, '/project', 'browser-sha', [
      { relativePath: 'entities/hash.txt', postimage: 'abc' },
      { relativePath: 'entities/obsolete.txt', delete: true },
    ]);
    return JSON.parse(files.get('/project/system/transactions/browser-sha/manifest.json') || '{}');
  });
  expect(result.targets[0].postimage.sha256).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  expect(result.targets[0].postimage.sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(result.targets.find((target: any) => target.relativePath === 'entities/obsolete.txt')).toMatchObject({ intent: 'delete', postimage: { present: false } });
});

test('completes a decided package after a browser-fallback mid-package rename', async ({ page }) => {
  await page.goto('http://localhost:3000');
  const result = await recoverAfterCrash(page, 'mid-rename');
  expect(result.files).toEqual(['after-a', undefined]);
  expect(result.repeatedRecovery).toEqual(result.files);
  expect(result.unrelated).toBe('keep');
  expect(result.marker).toContain('committed');
});

test('completes a fully-renamed package after a crash before the commit marker', async ({ page }) => {
  await page.goto('http://localhost:3000');
  const result = await recoverAfterCrash(page, 'after-last-rename-before-commit');
  expect(result.files).toEqual(['after-a', undefined]);
  expect(result.repeatedRecovery).toEqual(result.files);
  expect(result.unrelated).toBe('keep');
  expect(result.marker).toContain('committed');
});
