/**
 * Represents a workstream - a segment of work with associated metadata
 */
export interface Workstream {
  id: string;
  name: string;
  summary: string;
  tags: string[];
  metadata: WorkstreamMetadata;
  createdAt: string;
  updatedAt: string;
}

/**
 * Metadata for a workstream containing key project information
 */
export interface WorkstreamMetadata {
  hostIps?: string[];
  connectionInfo?: string;
  testingInfo?: string;
  [key: string]: any;
}

/**
 * Request to create a new workstream
 */
export interface CreateWorkstreamRequest {
  name: string;
  summary: string;
  tags?: string[];
  metadata?: WorkstreamMetadata;
}

/**
 * Request to update an existing workstream
 */
export interface UpdateWorkstreamRequest {
  id: string;
  name?: string;
  summary?: string;
  tags?: string[];
  metadata?: WorkstreamMetadata;
}

/**
 * Request to search workstreams by tags
 */
export interface SearchByTagsRequest {
  tags: string[];
  matchAll?: boolean; // If true, match all tags; if false, match any tag
}
