import type {
  CreateProjectInput,
  ExportArtifact,
  ExportProjectInput,
  Locale,
  NarrativeProject,
  ProjectTemplate,
  Proposal,
  StorageMode,
} from '../models/project';
import { createBlankProject, createStarterProject } from '../mock/seedProject';

const STORAGE_KEY = 'narrative-ide-project';
const LAST_PATH_KEY = 'narrative-ide-last-path';

type NodeRuntime = {
  fs: typeof import('fs');
  path: typeof import('path');
  process: NodeJS.Process;
  buffer: typeof import('buffer');
};

const getNodeRuntime = (): NodeRuntime | null => {
  const scope = globalThis as typeof globalThis & { require?: NodeRequire; process?: NodeJS.Process };
  const loader = scope.require;
  if (!loader) {
    return null;
  }

  try {
    return {
      fs: loader('fs'),
      path: loader('path'),
      process: scope.process || loader('process'),
      buffer: loader('buffer'),
    };
  } catch {
    return null;
  }
};

const slugify = (value: string) =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || 'narrative-project';

const writeJson = (fs: typeof import('fs'), filePath: string, payload: unknown) => {
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), 'utf8');
};

const ensureDir = (fs: typeof import('fs'), directory: string) => {
  if (!fs.existsSync(directory)) {
    fs.mkdirSync(directory, { recursive: true });
  }
};

const createProjectByTemplate = (
  template: ProjectTemplate,
  name: string,
  rootPath: string,
  locale: Locale,
  storageMode: StorageMode
) => {
  return template === 'blank'
    ? createBlankProject(name, rootPath, locale, storageMode)
    : createStarterProject(name, rootPath, locale, storageMode);
};

const serializeProjectToFolder = (
  project: NarrativeProject,
  runtime: NodeRuntime,
  rootPath: string
) => {
  const { fs, path } = runtime;
  ensureDir(fs, rootPath);

  const entitiesDir = path.join(rootPath, 'entities');
  const charactersDir = path.join(entitiesDir, 'characters');
  const timelineDir = path.join(entitiesDir, 'timeline');
  const worldDir = path.join(entitiesDir, 'world');
  const graphDir = path.join(entitiesDir, 'graph');
  const writingDir = path.join(rootPath, 'writing');
  const chaptersDir = path.join(writingDir, 'chapters');
  const scenesDir = path.join(writingDir, 'scenes');
  const systemDir = path.join(rootPath, 'system');
  const assetsDir = path.join(rootPath, 'assets');
  const exportsDir = path.join(rootPath, 'exports');

  [
    entitiesDir,
    charactersDir,
    timelineDir,
    worldDir,
    graphDir,
    writingDir,
    chaptersDir,
    scenesDir,
    systemDir,
    path.join(assetsDir, 'portraits'),
    path.join(assetsDir, 'world'),
    path.join(assetsDir, 'maps'),
    path.join(assetsDir, 'graph'),
    path.join(exportsDir, 'markdown'),
    path.join(exportsDir, 'html'),
  ].forEach((directory) => ensureDir(fs, directory));

  writeJson(fs, path.join(rootPath, 'project.json'), {
    metadata: project.metadata,
    counts: {
      characters: project.characters.length,
      timelineEvents: project.timelineEvents.length,
      scenes: project.scenes.length,
      worldItems: project.worldItems.length,
      proposals: project.proposals.length,
      exports: project.exports.length,
    },
  });

  project.characters.forEach((character) => {
    writeJson(fs, path.join(charactersDir, `${character.id}.json`), character);
  });

  writeJson(fs, path.join(entitiesDir, 'candidates.json'), project.candidates);
  writeJson(fs, path.join(entitiesDir, 'relationships.json'), project.relationships);
  writeJson(fs, path.join(timelineDir, 'branches.json'), project.timelineBranches);
  project.timelineEvents.forEach((event) => {
    writeJson(fs, path.join(timelineDir, `${event.id}.json`), event);
  });
  writeJson(fs, path.join(worldDir, 'containers.json'), project.worldContainers);
  project.worldItems.forEach((item) => {
    writeJson(fs, path.join(worldDir, `${item.id}.json`), item);
  });
  project.graphBoards.forEach((board) => {
    writeJson(fs, path.join(graphDir, `${board.id}.json`), board);
  });
  project.chapters.forEach((chapter) => {
    writeJson(fs, path.join(chaptersDir, `${chapter.id}.json`), chapter);
  });
  project.scenes.forEach((scene) => {
    fs.writeFileSync(path.join(scenesDir, `${scene.id}.md`), scene.content, 'utf8');
    writeJson(fs, path.join(scenesDir, `${scene.id}.meta.json`), {
      ...scene,
      content: undefined,
    });
  });
  writeJson(fs, path.join(systemDir, 'inbox.json'), project.proposals);
  writeJson(fs, path.join(systemDir, 'history.json'), project.proposalHistory);
  writeJson(fs, path.join(systemDir, 'issues.json'), project.issues);
  writeJson(fs, path.join(systemDir, 'exports.json'), project.exports);
  writeJson(fs, path.join(systemDir, 'index-cache.json'), {
    unreadUpdates: project.unreadUpdates,
    archivedIds: project.archivedIds,
  });
};

const hydrateProjectMetadata = (
  project: NarrativeProject,
  rootPath: string,
  storageMode: StorageMode,
  locale?: Locale
): NarrativeProject => ({
  ...project,
  metadata: {
    ...project.metadata,
    rootPath,
    storageMode,
    locale: locale || project.metadata.locale,
    updatedAt: new Date().toISOString(),
  },
});

const getDefaultProjectDir = (runtime: NodeRuntime, projectName: string) => {
  const baseDir = runtime.path.join(runtime.process.cwd(), 'data', 'projects');
  ensureDir(runtime.fs, baseDir);
  return runtime.path.join(baseDir, slugify(projectName));
};

export const projectService = {
  createProject(input: CreateProjectInput): NarrativeProject {
    const runtime = getNodeRuntime();
    const fallbackRoot = `memory://${slugify(input.name)}`;
    const rootPath = input.rootPath || (runtime ? getDefaultProjectDir(runtime, input.name) : fallbackRoot);
    const project = hydrateProjectMetadata(
      createProjectByTemplate(input.template, input.name, rootPath, input.locale, runtime ? 'nodefs' : 'memory'),
      rootPath,
      runtime ? 'nodefs' : 'memory',
      input.locale
    );

    if (!runtime) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      localStorage.setItem(LAST_PATH_KEY, project.metadata.rootPath);
      return project;
    }

    serializeProjectToFolder(project, runtime, rootPath);
    localStorage.setItem(LAST_PATH_KEY, rootPath);
    return project;
  },

  openProject(rootPath?: string | null): NarrativeProject {
    const runtime = getNodeRuntime();
    const resolvedPath = rootPath || localStorage.getItem(LAST_PATH_KEY);

    if (!runtime) {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        return JSON.parse(stored) as NarrativeProject;
      }
      const project = createStarterProject();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(project));
      localStorage.setItem(LAST_PATH_KEY, project.metadata.rootPath);
      return project;
    }

    if (!resolvedPath || !runtime.fs.existsSync(resolvedPath)) {
      const project = this.createProject({
        name: 'Starter Demo Project',
        rootPath: getDefaultProjectDir(runtime, 'starter-demo-project'),
        template: 'starter-demo',
        locale: 'en',
      });
      return project;
    }

    const projectIndex = JSON.parse(runtime.fs.readFileSync(runtime.path.join(resolvedPath, 'project.json'), 'utf8'));
    const entitiesDir = runtime.path.join(resolvedPath, 'entities');
    const timelineDir = runtime.path.join(entitiesDir, 'timeline');
    const worldDir = runtime.path.join(entitiesDir, 'world');
    const graphDir = runtime.path.join(entitiesDir, 'graph');
    const chaptersDir = runtime.path.join(resolvedPath, 'writing', 'chapters');
    const scenesDir = runtime.path.join(resolvedPath, 'writing', 'scenes');
    const systemDir = runtime.path.join(resolvedPath, 'system');

    const readJsonFiles = (directory: string) =>
      runtime.fs
        .readdirSync(directory)
        .filter((fileName) => fileName.endsWith('.json'))
        .map((fileName) => JSON.parse(runtime.fs.readFileSync(runtime.path.join(directory, fileName), 'utf8')));

    const sceneMetas = runtime.fs
      .readdirSync(scenesDir)
      .filter((fileName) => fileName.endsWith('.meta.json'))
      .map((fileName) => JSON.parse(runtime.fs.readFileSync(runtime.path.join(scenesDir, fileName), 'utf8')));

    const exportsPath = runtime.path.join(systemDir, 'exports.json');
    const project: NarrativeProject = {
      metadata: projectIndex.metadata,
      characters: readJsonFiles(runtime.path.join(entitiesDir, 'characters')),
      candidates: JSON.parse(runtime.fs.readFileSync(runtime.path.join(entitiesDir, 'candidates.json'), 'utf8')),
      timelineBranches: JSON.parse(runtime.fs.readFileSync(runtime.path.join(timelineDir, 'branches.json'), 'utf8')),
      timelineEvents: readJsonFiles(timelineDir).filter((item) => item.id),
      relationships: JSON.parse(runtime.fs.readFileSync(runtime.path.join(entitiesDir, 'relationships.json'), 'utf8')),
      chapters: readJsonFiles(chaptersDir),
      scenes: sceneMetas.map((meta) => ({
        ...meta,
        content: runtime.fs.readFileSync(runtime.path.join(scenesDir, `${meta.id}.md`), 'utf8'),
      })),
      worldContainers: JSON.parse(runtime.fs.readFileSync(runtime.path.join(worldDir, 'containers.json'), 'utf8')),
      worldItems: readJsonFiles(worldDir).filter((item) => item.id),
      graphBoards: readJsonFiles(graphDir),
      proposals: JSON.parse(runtime.fs.readFileSync(runtime.path.join(systemDir, 'inbox.json'), 'utf8')),
      proposalHistory: JSON.parse(runtime.fs.readFileSync(runtime.path.join(systemDir, 'history.json'), 'utf8')),
      issues: JSON.parse(runtime.fs.readFileSync(runtime.path.join(systemDir, 'issues.json'), 'utf8')),
      exports: runtime.fs.existsSync(exportsPath)
        ? JSON.parse(runtime.fs.readFileSync(exportsPath, 'utf8'))
        : [],
      ...JSON.parse(runtime.fs.readFileSync(runtime.path.join(systemDir, 'index-cache.json'), 'utf8')),
    };

    localStorage.setItem(LAST_PATH_KEY, resolvedPath);
    return hydrateProjectMetadata(project, resolvedPath, 'nodefs', project.metadata.locale);
  },

  saveProject(project: NarrativeProject): NarrativeProject {
    const runtime = getNodeRuntime();
    const updatedProject = hydrateProjectMetadata(project, project.metadata.rootPath, runtime ? 'nodefs' : 'memory', project.metadata.locale);
    if (!runtime) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedProject));
      localStorage.setItem(LAST_PATH_KEY, updatedProject.metadata.rootPath);
      return updatedProject;
    }

    serializeProjectToFolder(updatedProject, runtime, updatedProject.metadata.rootPath);
    localStorage.setItem(LAST_PATH_KEY, updatedProject.metadata.rootPath);
    return updatedProject;
  },

  async importAsset(file: File, assetKind: 'portraits' | 'maps' | 'world' | 'graph', projectRoot: string): Promise<string> {
    const runtime = getNodeRuntime();
    if (!runtime || projectRoot.startsWith('memory://')) {
      return await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
    }

    const safeName = `${Date.now()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, '-')}`;
    const targetDir = runtime.path.join(projectRoot, 'assets', assetKind);
    ensureDir(runtime.fs, targetDir);
    const buffer = runtime.buffer.Buffer.from(await file.arrayBuffer());
    const targetPath = runtime.path.join(targetDir, safeName);
    runtime.fs.writeFileSync(targetPath, buffer);
    return targetPath;
  },

  exportProject(project: NarrativeProject, input: ExportProjectInput): ExportArtifact {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const baseName = slugify(project.metadata.name);
    const fileName = `${baseName}-${timestamp}.${input.format === 'markdown' ? 'md' : 'html'}`;
    const preview = this.renderExport(project, input);
    const runtime = getNodeRuntime();

    if (!runtime || project.metadata.rootPath.startsWith('memory://')) {
      return {
        id: `export_${timestamp}`,
        format: input.format,
        fileName,
        path: null,
        createdAt: new Date().toISOString(),
        preview,
      };
    }

    const exportDir = runtime.path.join(project.metadata.rootPath, 'exports', input.format === 'markdown' ? 'markdown' : 'html');
    ensureDir(runtime.fs, exportDir);
    const exportPath = runtime.path.join(exportDir, fileName);
    runtime.fs.writeFileSync(exportPath, preview, 'utf8');
    return {
      id: `export_${timestamp}`,
      format: input.format,
      fileName,
      path: exportPath,
      createdAt: new Date().toISOString(),
      preview,
    };
  },

  renderExport(project: NarrativeProject, input: ExportProjectInput): string {
    const sceneBlocks = project.chapters
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((chapter) => {
        const scenes = project.scenes
          .filter((scene) => scene.chapterId === chapter.id)
          .sort((a, b) => a.orderIndex - b.orderIndex)
          .map((scene) => `## ${scene.title}\n\n${scene.content || scene.summary}`)
          .join('\n\n');
        return `# ${chapter.title}\n\n${chapter.summary}\n\n${scenes}`;
      })
      .join('\n\n');

    const appendices = input.includeAppendices
      ? `\n\n# Appendices\n\n## Characters\n${project.characters
          .map((character) => `- ${character.name}: ${character.summary}`)
          .join('\n')}\n\n## Timeline\n${project.timelineEvents
          .map((event) => `- ${event.title} (${event.time || 'n/a'})`)
          .join('\n')}`
      : '';

    if (input.format === 'markdown') {
      return `# ${project.metadata.name}\n\n${sceneBlocks}${appendices}`;
    }

    return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${project.metadata.name}</title><style>body{font-family:Georgia,serif;max-width:900px;margin:40px auto;line-height:1.7;color:#111}h1,h2{font-family:Arial,sans-serif}</style></head><body><h1>${project.metadata.name}</h1>${project.chapters
      .sort((a, b) => a.orderIndex - b.orderIndex)
      .map((chapter) => {
        const scenes = project.scenes
          .filter((scene) => scene.chapterId === chapter.id)
          .sort((a, b) => a.orderIndex - b.orderIndex)
          .map((scene) => `<h2>${scene.title}</h2><p>${(scene.content || scene.summary).replace(/\n/g, '<br/>')}</p>`)
          .join('');
        return `<section><h1>${chapter.title}</h1><p>${chapter.summary}</p>${scenes}</section>`;
      })
      .join('')}${input.includeAppendices ? `<section><h1>Appendices</h1><h2>Characters</h2><ul>${project.characters
        .map((character) => `<li><strong>${character.name}</strong>: ${character.summary}</li>`)
        .join('')}</ul></section>` : ''}</body></html>`;
  },

  resolveProposal(project: NarrativeProject, proposalId: string, nextStatus: Proposal['status']): NarrativeProject {
    const target = project.proposals.find((proposal) => proposal.id === proposalId);
    if (!target) {
      return project;
    }

    const resolvedProposal: Proposal = {
      ...target,
      status: nextStatus,
      resolvedAt: new Date().toISOString(),
    };

    return {
      ...project,
      proposals: project.proposals.filter((proposal) => proposal.id !== proposalId),
      proposalHistory: [resolvedProposal, ...project.proposalHistory],
      unreadUpdates: {
        ...project.unreadUpdates,
        entities: {
          ...project.unreadUpdates.entities,
          [proposalId]: false,
        },
        activities: {
          ...project.unreadUpdates.activities,
          workbench: project.proposals.length > 1,
        },
        sections: {
          ...project.unreadUpdates.sections,
          'workbench.inbox': project.proposals.length > 1,
        },
      },
    };
  },
};
