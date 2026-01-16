#!/usr/bin/env node
import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { WorkstreamStorage } from './storage.js';
import { CreateWorkstreamRequest, UpdateWorkstreamRequest, SearchByTagsRequest } from './types.js';

/**
 * Local Memory MCP Server
 * Organizes work into segments (workstreams) with tagging and metadata
 */
class LocalMemServer {
  private server: Server;
  private storage: WorkstreamStorage;

  constructor() {
    this.server = new Server(
      {
        name: 'local-mem',
        version: '1.0.0',
      },
      {
        capabilities: {
          tools: {},
          resources: {},
        },
      }
    );

    this.storage = new WorkstreamStorage();
    this.setupHandlers();
  }

  private setupHandlers(): void {
    // List available tools
    this.server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: [
        {
          name: 'create_workstream',
          description: 'Create a new workstream (work segment) with name, summary, tags, and metadata',
          inputSchema: {
            type: 'object',
            properties: {
              name: {
                type: 'string',
                description: 'Name of the workstream',
              },
              summary: {
                type: 'string',
                description: 'Summary/description of the workstream',
              },
              tags: {
                type: 'array',
                items: { type: 'string' },
                description: 'Tags to organize the workstream (optional)',
              },
              metadata: {
                type: 'object',
                description: 'Additional metadata like hostIps, connectionInfo, testingInfo (optional)',
                properties: {
                  hostIps: {
                    type: 'array',
                    items: { type: 'string' },
                    description: 'Host IP addresses',
                  },
                  connectionInfo: {
                    type: 'string',
                    description: 'How to connect to the system',
                  },
                  testingInfo: {
                    type: 'string',
                    description: 'How to test the system',
                  },
                },
              },
            },
            required: ['name', 'summary'],
          },
        },
        {
          name: 'list_workstreams',
          description: 'List all workstreams',
          inputSchema: {
            type: 'object',
            properties: {},
          },
        },
        {
          name: 'get_workstream',
          description: 'Get detailed information about a specific workstream by ID',
          inputSchema: {
            type: 'object',
            properties: {
              id: {
                type: 'string',
                description: 'Workstream ID',
              },
            },
            required: ['id'],
          },
        },
        {
          name: 'update_workstream',
          description: 'Update an existing workstream',
          inputSchema: {
            type: 'object',
            properties: {
              id: {
                type: 'string',
                description: 'Workstream ID',
              },
              name: {
                type: 'string',
                description: 'New name (optional)',
              },
              summary: {
                type: 'string',
                description: 'New summary (optional)',
              },
              tags: {
                type: 'array',
                items: { type: 'string' },
                description: 'New tags (optional, replaces existing)',
              },
              metadata: {
                type: 'object',
                description: 'Metadata to merge with existing (optional)',
              },
            },
            required: ['id'],
          },
        },
        {
          name: 'delete_workstream',
          description: 'Delete a workstream by ID',
          inputSchema: {
            type: 'object',
            properties: {
              id: {
                type: 'string',
                description: 'Workstream ID',
              },
            },
            required: ['id'],
          },
        },
        {
          name: 'add_tags',
          description: 'Add tags to an existing workstream',
          inputSchema: {
            type: 'object',
            properties: {
              id: {
                type: 'string',
                description: 'Workstream ID',
              },
              tags: {
                type: 'array',
                items: { type: 'string' },
                description: 'Tags to add',
              },
            },
            required: ['id', 'tags'],
          },
        },
        {
          name: 'search_by_tags',
          description: 'Search workstreams by tags',
          inputSchema: {
            type: 'object',
            properties: {
              tags: {
                type: 'array',
                items: { type: 'string' },
                description: 'Tags to search for',
              },
              matchAll: {
                type: 'boolean',
                description: 'If true, match all tags; if false, match any tag (default: false)',
              },
            },
            required: ['tags'],
          },
        },
        {
          name: 'search_workstreams',
          description: 'Search workstreams by name or summary text',
          inputSchema: {
            type: 'object',
            properties: {
              query: {
                type: 'string',
                description: 'Search query',
              },
            },
            required: ['query'],
          },
        },
      ],
    }));

    // Handle tool calls
    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case 'create_workstream': {
            const workstream = await this.storage.create(args as any as CreateWorkstreamRequest);
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstream, null, 2),
                },
              ],
            };
          }

          case 'list_workstreams': {
            const workstreams = await this.storage.list();
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstreams, null, 2),
                },
              ],
            };
          }

          case 'get_workstream': {
            const { id } = args as { id: string };
            const workstream = await this.storage.get(id);
            if (!workstream) {
              return {
                content: [
                  {
                    type: 'text',
                    text: `Workstream with ID "${id}" not found`,
                  },
                ],
                isError: true,
              };
            }
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstream, null, 2),
                },
              ],
            };
          }

          case 'update_workstream': {
            const workstream = await this.storage.update(args as any as UpdateWorkstreamRequest);
            if (!workstream) {
              return {
                content: [
                  {
                    type: 'text',
                    text: `Workstream with ID "${(args as any as UpdateWorkstreamRequest).id}" not found`,
                  },
                ],
                isError: true,
              };
            }
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstream, null, 2),
                },
              ],
            };
          }

          case 'delete_workstream': {
            const { id } = args as { id: string };
            const deleted = await this.storage.delete(id);
            return {
              content: [
                {
                  type: 'text',
                  text: deleted
                    ? `Workstream "${id}" deleted successfully`
                    : `Workstream "${id}" not found`,
                },
              ],
              isError: !deleted,
            };
          }

          case 'add_tags': {
            const { id, tags } = args as { id: string; tags: string[] };
            const workstream = await this.storage.addTags(id, tags);
            if (!workstream) {
              return {
                content: [
                  {
                    type: 'text',
                    text: `Workstream with ID "${id}" not found`,
                  },
                ],
                isError: true,
              };
            }
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstream, null, 2),
                },
              ],
            };
          }

          case 'search_by_tags': {
            const { tags, matchAll = false } = args as any as SearchByTagsRequest;
            const workstreams = await this.storage.searchByTags(tags, matchAll);
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstreams, null, 2),
                },
              ],
            };
          }

          case 'search_workstreams': {
            const { query } = args as { query: string };
            const workstreams = await this.storage.search(query);
            return {
              content: [
                {
                  type: 'text',
                  text: JSON.stringify(workstreams, null, 2),
                },
              ],
            };
          }

          default:
            return {
              content: [
                {
                  type: 'text',
                  text: `Unknown tool: ${name}`,
                },
              ],
              isError: true,
            };
        }
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error executing tool ${name}: ${error}`,
            },
          ],
          isError: true,
        };
      }
    });

    // List available resources
    this.server.setRequestHandler(ListResourcesRequestSchema, async () => {
      const workstreams = await this.storage.list();
      return {
        resources: workstreams.map((w) => ({
          uri: `workstream://${w.id}`,
          name: w.name,
          description: w.summary,
          mimeType: 'application/json',
        })),
      };
    });

    // Read resource content
    this.server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
      const uri = request.params.uri;
      
      if (!uri.startsWith('workstream://')) {
        throw new Error('Invalid resource URI');
      }

      const id = uri.replace('workstream://', '');
      const workstream = await this.storage.get(id);

      if (!workstream) {
        throw new Error(`Workstream ${id} not found`);
      }

      return {
        contents: [
          {
            uri,
            mimeType: 'application/json',
            text: JSON.stringify(workstream, null, 2),
          },
        ],
      };
    });
  }

  async run(): Promise<void> {
    // Initialize storage
    await this.storage.initialize();

    // Connect server to stdio transport
    const transport = new StdioServerTransport();
    await this.server.connect(transport);

    console.error('Local Memory MCP Server running on stdio');
  }
}

// Start the server
const server = new LocalMemServer();
server.run().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});
