import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { cp, mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { once } from 'node:events';
import { _electron as electron } from 'playwright';
import { createServer as createViteServer } from 'vite';

const REPO_ROOT = process.cwd();
const SOURCE_PROJECT = process.env.NARRATIVE_IDE_IMPORT_FIXTURE;
const IN_PLACE = process.env.NARRATIVE_IDE_IMPORT_IN_PLACE === '1';
const STAGE_TIMEOUT_MS = 90_000;
const resources = { app: null, vite: null };
const startedAt = Date.now();

if (!SOURCE_PROJECT) throw new Error('NARRATIVE_IDE_IMPORT_FIXTURE is required.');

const log = (stage, message) =>
  console.log(`[w1-package-compiler +${Date.now() - startedAt}ms] ${stage}: ${message}`);

async function stage(name, operation, timeoutMs = STAGE_TIMEOUT_MS) {
  log(name, 'start');
  let timer;
  try {
    const result = await Promise.race([
      Promise.resolve().then(operation),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${name} timed out after ${timeoutMs}ms`)), timeoutMs);
      }),
    ]);
    log(name, 'complete');
    return result;
  } finally {
    clearTimeout(timer);
  }
}

function noCredentialEnv() {
  return Object.fromEntries(
    Object.entries(process.env).filter(([key]) => !/(api[_-]?key|openai|deepseek|anthropic|gemini)/i.test(key)),
  );
}

async function closeApp() {
  const app = resources.app;
  resources.app = null;
  if (!app) return;
  const child = app.process();
  try {
    await stage('electron.close', async () => {
      if (!child || child.exitCode !== null) return;
      const exited = once(child, 'exit');
      await app.evaluate(({ app: electronApp }) => electronApp.quit());
      if (child.exitCode === null) await exited;
    }, 15_000);
  } catch {
    child?.kill('SIGKILL');
  }
}

async function launch(rendererUrl, userData, projectRoot) {
  resources.app = await stage('electron.launch', () => electron.launch({
    args: ['.'],
    cwd: REPO_ROOT,
    env: {
      ...noCredentialEnv(),
      NARRATIVE_IDE_RENDERER_URL: rendererUrl,
      NARRATIVE_IDE_USER_DATA: userData,
      NARRATIVE_IDE_RUNTIME_SMOKE: '1',
      NARRATIVE_IDE_SMOKE_PROJECT_ROOT: projectRoot,
    },
  }));
  const page = await stage('electron.window', () => resources.app.firstWindow());
  page.on('dialog', (dialog) => dialog.dismiss().catch(() => {}));
  await stage('renderer.ready', () => page.waitForSelector('[data-testid="activity-btn-workbench"]'));
  return page;
}

async function openProject(page) {
  await page.getByTestId('toolbar-open-project').click();
  await page.getByTestId('project-dialog').waitFor({ state: 'visible' });
  await page.getByTestId('project-folder-pick').click();
  await page.getByTestId('project-folder-input').waitFor({ state: 'visible' });
  await page.getByTestId('project-dialog-submit').click();
  await page.getByTestId('project-dialog').waitFor({ state: 'hidden' });
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('sidebar-section-workbench-inbox').click();
  await page.getByTestId('workbench-inbox-list').waitFor({ state: 'visible' });
}

async function snapshot(page) {
  return page.evaluate(() => {
    const state = window.__narrativeStore.getState();
    return {
      proposals: state.proposals.map((proposal) => ({
        id: proposal.id,
        status: proposal.status,
        lastBlockReason: proposal.lastBlockReason ?? null,
        packageCompiler: proposal.packageCompiler ?? null,
      })),
      history: state.proposalHistory.map((proposal) => proposal.id),
      counts: {
        chapters: state.chapters.length,
        scenes: state.scenes.length,
        manuscriptNodes: state.manuscriptNodes.length,
        characters: state.characters.length,
        events: state.timelineEvents.length,
        worldItems: state.worldItems.length,
      },
    };
  });
}

async function waitFor(predicate, description) {
  const deadline = Date.now() + STAGE_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${description}.`);
}

async function main() {
  const temporaryRoot = IN_PLACE ? null : await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-import-compiler-'));
  const projectRoot = IN_PLACE ? path.resolve(SOURCE_PROJECT) : path.join(temporaryRoot, 'project');
  const outputRoot = path.join('/tmp', `narrative-ide-import-compiler-result-${Date.now()}`);
  const userData = await mkdtemp(path.join(os.tmpdir(), 'narrative-ide-import-compiler-user-'));
  try {
    if (!IN_PLACE) await stage('project.copy', () => cp(SOURCE_PROJECT, projectRoot, { recursive: true }));
    await mkdir(outputRoot, { recursive: true });
    resources.vite = await stage('vite.create', () => createViteServer({
      root: REPO_ROOT,
      logLevel: 'error',
      server: { host: '127.0.0.1', port: 0 },
    }));
    await stage('vite.listen', () => resources.vite.listen());
    const rendererUrl = resources.vite.resolvedUrls?.local?.[0];
    assert(rendererUrl, 'Vite did not expose a renderer URL.');

    let page = await launch(rendererUrl, userData, projectRoot);
    await openProject(page);
    const before = await snapshot(page);
    assert(before.proposals.length > 0, 'Fixture has no pending import package.');
    assert(before.proposals.every((proposal) =>
      proposal.packageCompiler?.contractVersion === 'w1-package-graph-v2'
    ), 'Pending proposals do not contain the package compiler contract.');

    const repair = page.locator('[data-testid^="repair-blocked-package-"]');
    const accept = page.locator('[data-testid^="accept-import-package-"]');
    if (await repair.isVisible()) {
      await stage('package.repair', () => repair.click());
      await stage('package.repair.valid', () => accept.waitFor({ state: 'visible' }));
    }
    assert.equal(await accept.count(), 1, 'Expected exactly one complete package Accept action.');
    await stage('package.accept', () => accept.click());
    await stage('package.persist', () => waitFor(async () => (await snapshot(page)).proposals.length === 0, 'package acceptance'));
    const accepted = await snapshot(page);
    assert.equal(accepted.history.length, before.proposals.length, 'Every package proposal must be accepted exactly once.');
    assert.deepEqual(
      { chapters: accepted.counts.chapters, scenes: accepted.counts.scenes, manuscriptNodes: accepted.counts.manuscriptNodes },
      { chapters: 10, scenes: 10, manuscriptNodes: 20 },
    );
    await page.screenshot({ path: path.join(outputRoot, 'accepted.png'), fullPage: true });
    await closeApp();

    page = await launch(rendererUrl, userData, projectRoot);
    await openProject(page);
    const restarted = await snapshot(page);
    assert.equal(restarted.proposals.length, 0, 'Accepted package returned after restart.');
    assert.deepEqual(restarted.counts, accepted.counts, 'Canonical counts changed after restart.');
    await writeFile(path.join(outputRoot, 'result.json'), `${JSON.stringify({
      status: 'PASS',
      inPlace: IN_PLACE,
      projectRoot,
      proposalCount: before.proposals.length,
      accepted: accepted.counts,
      restarted: restarted.counts,
    }, null, 2)}\n`);
    log('result', `PASS ${outputRoot}`);
  } finally {
    await closeApp();
    if (resources.vite) await resources.vite.close();
    await rm(userData, { recursive: true, force: true });
    if (temporaryRoot) await rm(temporaryRoot, { recursive: true, force: true });
  }
}

await main();
