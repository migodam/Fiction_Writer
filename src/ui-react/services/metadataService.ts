import type { MetadataFile, MetadataChunk, MetadataFileType } from '../models/project';

type NodeRuntime = {
  fs: typeof import('fs');
  path: typeof import('path');
};

const getNodeRuntime = (): NodeRuntime | null => {
  const scope = globalThis as typeof globalThis & { require?: NodeRequire };
  const loader = scope.require;
  if (!loader) return null;
  try {
    return {
      fs: loader('fs'),
      path: loader('path'),
    };
  } catch {
    return null;
  }
};

const ensureDir = (fs: typeof import('fs'), dir: string): void => {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
};

const writeJson = (fs: typeof import('fs'), filePath: string, payload: unknown): void => {
  fs.writeFileSync(filePath, JSON.stringify(payload, null, 2), 'utf8');
};

const safeReadJson = <T>(fs: typeof import('fs'), filePath: string, fallback: T): T => {
  return fs.existsSync(filePath) ? (JSON.parse(fs.readFileSync(filePath, 'utf8') as string) as T) : fallback;
};

const metaDir = (root: string) => `${root}/metadata`;
const fileDir = (root: string, id: string) => `${root}/metadata/${id}`;

export function loadMetadataIndex(projectRoot: string): MetadataFile[] {
  const rt = getNodeRuntime();
  if (!rt) return [];
  return safeReadJson<MetadataFile[]>(rt.fs, `${metaDir(projectRoot)}/index.json`, []);
}

export function saveMetadataIndex(projectRoot: string, files: MetadataFile[]): void {
  const rt = getNodeRuntime();
  if (!rt) return;
  ensureDir(rt.fs, metaDir(projectRoot));
  writeJson(rt.fs, `${metaDir(projectRoot)}/index.json`, files);
}

export function chunkText(text: string, fileId: string): MetadataChunk[] {
  const words = text.split(/\s+/).filter(Boolean);
  const CHUNK_SIZE = 500;
  const chunks: MetadataChunk[] = [];
  for (let i = 0; i < words.length; i += CHUNK_SIZE) {
    const chunkWords = words.slice(i, i + CHUNK_SIZE);
    const content = chunkWords.join(' ');
    chunks.push({
      id: `chunk_${fileId}_${chunks.length}`,
      fileId,
      index: chunks.length,
      content,
      tokenCount: chunkWords.length,
    });
  }
  return chunks;
}

export function importFile(
  projectRoot: string,
  filePath: string,
  meta: Pick<MetadataFile, 'type' | 'tags' | 'description'>
): MetadataFile {
  const rt = getNodeRuntime();
  if (!rt) {
    throw new Error('Node runtime not available — cannot import files in browser mode.');
  }

  const text = rt.fs.readFileSync(filePath, 'utf-8') as string;
  const filename = filePath.split(/[\\/]/).pop() ?? filePath;
  const extMatch = filename.match(/\.([^.]+)$/);
  const originalExt = extMatch ? extMatch[1].toLowerCase() : 'txt';

  let content = text;
  if (originalExt === 'md') {
    content = text
      .replace(/#{1,6}\s+/g, '')
      .replace(/[*_`~]/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
  }

  const fileId = `meta_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const dir = fileDir(projectRoot, fileId);
  ensureDir(rt.fs, dir);

  rt.fs.writeFileSync(`${dir}/original.${originalExt}`, text, 'utf-8');

  const chunks = chunkText(content, fileId);
  writeJson(rt.fs, `${dir}/chunks.json`, chunks);

  const file: MetadataFile = {
    id: fileId,
    filename,
    originalExt,
    type: meta.type,
    tags: meta.tags,
    description: meta.description,
    importedAt: new Date().toISOString(),
    chunkCount: chunks.length,
    status: 'ready',
  };

  const index = loadMetadataIndex(projectRoot);
  saveMetadataIndex(projectRoot, [...index, file]);

  return file;
}

export function deleteFile(projectRoot: string, fileId: string): void {
  const rt = getNodeRuntime();
  if (!rt) return;
  const dir = fileDir(projectRoot, fileId);
  if (rt.fs.existsSync(dir)) {
    rt.fs.rmSync(dir, { recursive: true });
  }
  const index = loadMetadataIndex(projectRoot);
  saveMetadataIndex(projectRoot, index.filter((f) => f.id !== fileId));
}

export function loadChunks(projectRoot: string, fileId: string): MetadataChunk[] {
  const rt = getNodeRuntime();
  if (!rt) return [];
  return safeReadJson<MetadataChunk[]>(rt.fs, `${fileDir(projectRoot, fileId)}/chunks.json`, []);
}

export type { MetadataFileType };
