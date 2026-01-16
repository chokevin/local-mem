#!/usr/bin/env node
/**
 * Test script for the local-mem MCP server
 * This simulates MCP client requests to test functionality
 */

import { spawn } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

class MCPClient {
  constructor() {
    this.server = null;
    this.requestId = 1;
  }

  start() {
    return new Promise((resolve, reject) => {
      this.server = spawn('node', [join(__dirname, '../dist/index.js')], {
        stdio: ['pipe', 'pipe', 'pipe']
      });

      this.server.stderr.on('data', (data) => {
        console.error(`[Server]: ${data.toString()}`);
        if (data.toString().includes('running on stdio')) {
          resolve();
        }
      });

      this.server.on('error', reject);
    });
  }

  sendRequest(method, params = {}) {
    return new Promise((resolve, reject) => {
      const request = {
        jsonrpc: '2.0',
        id: this.requestId++,
        method,
        params
      };

      let responseData = '';

      const handleData = (data) => {
        responseData += data.toString();
        try {
          const lines = responseData.split('\n');
          for (const line of lines) {
            if (line.trim()) {
              const response = JSON.parse(line);
              if (response.id === request.id) {
                this.server.stdout.removeListener('data', handleData);
                resolve(response);
                return;
              }
            }
          }
        } catch (e) {
          // Not complete JSON yet, keep accumulating
        }
      };

      this.server.stdout.on('data', handleData);

      setTimeout(() => {
        this.server.stdout.removeListener('data', handleData);
        reject(new Error('Request timeout'));
      }, 5000);

      this.server.stdin.write(JSON.stringify(request) + '\n');
    });
  }

  stop() {
    if (this.server) {
      this.server.kill();
    }
  }
}

async function runTests() {
  const client = new MCPClient();
  
  try {
    console.log('Starting MCP server...');
    await client.start();
    console.log('✓ Server started');

    // Test 1: Initialize
    console.log('\nTest 1: Initialize connection');
    const initResponse = await client.sendRequest('initialize', {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: {
        name: 'test-client',
        version: '1.0.0'
      }
    });
    console.log('✓ Initialize successful');

    // Test 2: List tools
    console.log('\nTest 2: List available tools');
    const toolsResponse = await client.sendRequest('tools/list');
    console.log(`✓ Found ${toolsResponse.result.tools.length} tools`);
    console.log('  Tools:', toolsResponse.result.tools.map(t => t.name).join(', '));

    // Test 3: Create a workstream
    console.log('\nTest 3: Create a workstream');
    const createResponse = await client.sendRequest('tools/call', {
      name: 'create_workstream',
      arguments: {
        name: 'Test Project',
        summary: 'A test workstream for validation',
        tags: ['test', 'demo'],
        metadata: {
          hostIps: ['192.168.1.100'],
          connectionInfo: 'ssh user@192.168.1.100',
          testingInfo: 'npm test'
        }
      }
    });
    const workstream = JSON.parse(createResponse.result.content[0].text);
    console.log(`✓ Created workstream: ${workstream.name} (${workstream.id})`);

    // Test 4: List workstreams
    console.log('\nTest 4: List all workstreams');
    const listResponse = await client.sendRequest('tools/call', {
      name: 'list_workstreams',
      arguments: {}
    });
    const workstreams = JSON.parse(listResponse.result.content[0].text);
    console.log(`✓ Found ${workstreams.length} workstream(s)`);

    // Test 5: Get specific workstream
    console.log('\nTest 5: Get workstream details');
    const getResponse = await client.sendRequest('tools/call', {
      name: 'get_workstream',
      arguments: {
        id: workstream.id
      }
    });
    const retrieved = JSON.parse(getResponse.result.content[0].text);
    console.log(`✓ Retrieved: ${retrieved.name}`);

    // Test 6: Add tags
    console.log('\nTest 6: Add tags to workstream');
    const addTagsResponse = await client.sendRequest('tools/call', {
      name: 'add_tags',
      arguments: {
        id: workstream.id,
        tags: ['production', 'important']
      }
    });
    const updated = JSON.parse(addTagsResponse.result.content[0].text);
    console.log(`✓ Tags updated: ${updated.tags.join(', ')}`);

    // Test 7: Search by tags
    console.log('\nTest 7: Search by tags');
    const searchResponse = await client.sendRequest('tools/call', {
      name: 'search_by_tags',
      arguments: {
        tags: ['test'],
        matchAll: false
      }
    });
    const searchResults = JSON.parse(searchResponse.result.content[0].text);
    console.log(`✓ Found ${searchResults.length} workstream(s) with tag 'test'`);

    // Test 8: List resources
    console.log('\nTest 8: List resources');
    const resourcesResponse = await client.sendRequest('resources/list');
    console.log(`✓ Found ${resourcesResponse.result.resources.length} resource(s)`);

    console.log('\n✅ All tests passed!');
    
  } catch (error) {
    console.error('\n❌ Test failed:', error);
    process.exit(1);
  } finally {
    client.stop();
  }
}

runTests();
