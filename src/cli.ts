#!/usr/bin/env node
/**
 * CLI utility for interacting with local-mem workstreams
 * Useful for debugging and quick access to workstream data
 */

import { WorkstreamStorage } from './storage.js';
import { dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  const storage = new WorkstreamStorage();
  await storage.initialize();

  switch (command) {
    case 'list':
    case 'ls': {
      const workstreams = await storage.list();
      if (workstreams.length === 0) {
        console.log('No workstreams found.');
      } else {
        console.log(`\nFound ${workstreams.length} workstream(s):\n`);
        workstreams.forEach((w) => {
          console.log(`ID: ${w.id}`);
          console.log(`Name: ${w.name}`);
          console.log(`Summary: ${w.summary}`);
          console.log(`Tags: ${w.tags.join(', ')}`);
          console.log(`Created: ${w.createdAt}`);
          console.log(`Updated: ${w.updatedAt}`);
          if (Object.keys(w.metadata).length > 0) {
            console.log('Metadata:', JSON.stringify(w.metadata, null, 2));
          }
          console.log('---');
        });
      }
      break;
    }

    case 'get': {
      const id = args[1];
      if (!id) {
        console.error('Error: Please provide a workstream ID');
        process.exit(1);
      }
      const workstream = await storage.get(id);
      if (!workstream) {
        console.error(`Workstream ${id} not found`);
        process.exit(1);
      }
      console.log(JSON.stringify(workstream, null, 2));
      break;
    }

    case 'search': {
      const query = args.slice(1).join(' ');
      if (!query) {
        console.error('Error: Please provide a search query');
        process.exit(1);
      }
      const results = await storage.search(query);
      console.log(`Found ${results.length} result(s):`);
      results.forEach((w) => {
        console.log(`- ${w.name} (${w.id})`);
        console.log(`  ${w.summary}`);
      });
      break;
    }

    case 'tags': {
      const tags = args.slice(1);
      if (tags.length === 0) {
        console.error('Error: Please provide at least one tag');
        process.exit(1);
      }
      const results = await storage.searchByTags(tags, false);
      console.log(`Found ${results.length} workstream(s) with tags: ${tags.join(', ')}`);
      results.forEach((w) => {
        console.log(`- ${w.name} (${w.id})`);
        console.log(`  Tags: ${w.tags.join(', ')}`);
      });
      break;
    }

    case 'help':
    case undefined: {
      console.log(`
local-mem CLI utility

Usage:
  local-mem <command> [options]

Commands:
  list, ls              List all workstreams
  get <id>              Get a workstream by ID
  search <query>        Search workstreams by name or summary
  tags <tag1> [tag2]    Search workstreams by tags
  help                  Show this help message

Examples:
  local-mem list
  local-mem get ws-1234567890-abc123
  local-mem search "API project"
  local-mem tags backend nodejs
      `);
      break;
    }

    default:
      console.error(`Unknown command: ${command}`);
      console.error('Run "local-mem help" for usage information');
      process.exit(1);
  }
}

main().catch((error) => {
  console.error('Error:', error);
  process.exit(1);
});
