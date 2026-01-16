import { promises as fs } from 'fs';
import * as path from 'path';
import { Workstream, CreateWorkstreamRequest, UpdateWorkstreamRequest } from './types.js';

/**
 * File-based storage for workstreams
 */
export class WorkstreamStorage {
  private dataDir: string;
  private dataFile: string;
  private workstreams: Map<string, Workstream>;

  constructor(dataDir: string = './data') {
    this.dataDir = dataDir;
    this.dataFile = path.join(dataDir, 'workstreams.json');
    this.workstreams = new Map();
  }

  /**
   * Initialize storage by creating data directory and loading existing data
   */
  async initialize(): Promise<void> {
    try {
      await fs.mkdir(this.dataDir, { recursive: true });
      await this.load();
    } catch (error) {
      console.error('Failed to initialize storage:', error);
      throw error;
    }
  }

  /**
   * Load workstreams from file
   */
  private async load(): Promise<void> {
    try {
      const data = await fs.readFile(this.dataFile, 'utf-8');
      const workstreamsArray: Workstream[] = JSON.parse(data);
      this.workstreams = new Map(workstreamsArray.map(w => [w.id, w]));
    } catch (error: any) {
      if (error.code === 'ENOENT') {
        // File doesn't exist yet, start with empty map
        this.workstreams = new Map();
      } else {
        throw error;
      }
    }
  }

  /**
   * Save workstreams to file
   */
  private async save(): Promise<void> {
    const workstreamsArray = Array.from(this.workstreams.values());
    await fs.writeFile(this.dataFile, JSON.stringify(workstreamsArray, null, 2), 'utf-8');
  }

  /**
   * Generate a unique ID for a workstream
   */
  private generateId(): string {
    return `ws-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Create a new workstream
   */
  async create(request: CreateWorkstreamRequest): Promise<Workstream> {
    const now = new Date().toISOString();
    const workstream: Workstream = {
      id: this.generateId(),
      name: request.name,
      summary: request.summary,
      tags: request.tags || [],
      metadata: request.metadata || {},
      createdAt: now,
      updatedAt: now,
    };

    this.workstreams.set(workstream.id, workstream);
    await this.save();
    return workstream;
  }

  /**
   * Get a workstream by ID
   */
  async get(id: string): Promise<Workstream | undefined> {
    return this.workstreams.get(id);
  }

  /**
   * List all workstreams
   */
  async list(): Promise<Workstream[]> {
    return Array.from(this.workstreams.values());
  }

  /**
   * Update a workstream
   */
  async update(request: UpdateWorkstreamRequest): Promise<Workstream | undefined> {
    const workstream = this.workstreams.get(request.id);
    if (!workstream) {
      return undefined;
    }

    const updated: Workstream = {
      ...workstream,
      name: request.name !== undefined ? request.name : workstream.name,
      summary: request.summary !== undefined ? request.summary : workstream.summary,
      tags: request.tags !== undefined ? request.tags : workstream.tags,
      metadata: request.metadata !== undefined ? { ...workstream.metadata, ...request.metadata } : workstream.metadata,
      updatedAt: new Date().toISOString(),
    };

    this.workstreams.set(updated.id, updated);
    await this.save();
    return updated;
  }

  /**
   * Delete a workstream
   */
  async delete(id: string): Promise<boolean> {
    const deleted = this.workstreams.delete(id);
    if (deleted) {
      await this.save();
    }
    return deleted;
  }

  /**
   * Add tags to a workstream
   */
  async addTags(id: string, tags: string[]): Promise<Workstream | undefined> {
    const workstream = this.workstreams.get(id);
    if (!workstream) {
      return undefined;
    }

    const uniqueTags = new Set([...workstream.tags, ...tags]);
    const updated: Workstream = {
      ...workstream,
      tags: Array.from(uniqueTags),
      updatedAt: new Date().toISOString(),
    };

    this.workstreams.set(updated.id, updated);
    await this.save();
    return updated;
  }

  /**
   * Search workstreams by tags
   */
  async searchByTags(tags: string[], matchAll: boolean = false): Promise<Workstream[]> {
    const workstreamsArray = Array.from(this.workstreams.values());
    
    if (matchAll) {
      // Match all tags
      return workstreamsArray.filter(w => 
        tags.every(tag => w.tags.includes(tag))
      );
    } else {
      // Match any tag
      return workstreamsArray.filter(w => 
        tags.some(tag => w.tags.includes(tag))
      );
    }
  }

  /**
   * Search workstreams by name or summary
   */
  async search(query: string): Promise<Workstream[]> {
    const workstreamsArray = Array.from(this.workstreams.values());
    const lowerQuery = query.toLowerCase();
    
    return workstreamsArray.filter(w => 
      w.name.toLowerCase().includes(lowerQuery) ||
      w.summary.toLowerCase().includes(lowerQuery)
    );
  }
}
