# Example Usage Guide

This guide demonstrates practical examples of using the local-mem MCP server to organize your work.

## Example 1: Managing Multiple Projects

### Creating Project Workstreams

**Frontend Project:**
```json
{
  "name": "E-commerce Frontend",
  "summary": "Next.js-based e-commerce platform frontend with Tailwind CSS",
  "tags": ["frontend", "nextjs", "ecommerce", "production"],
  "metadata": {
    "hostIps": ["staging.mysite.com:3000", "localhost:3000"],
    "connectionInfo": "npm run dev for local, ssh deploy@staging.mysite.com for staging",
    "testingInfo": "npm test && npm run e2e",
    "deploymentUrl": "https://staging.mysite.com",
    "envVars": "NEXT_PUBLIC_API_URL, STRIPE_PUBLIC_KEY"
  }
}
```

**Backend API:**
```json
{
  "name": "E-commerce API",
  "summary": "Node.js/Express REST API with PostgreSQL database",
  "tags": ["backend", "api", "nodejs", "postgresql"],
  "metadata": {
    "hostIps": ["10.0.1.50", "api.staging.mysite.com"],
    "connectionInfo": "ssh user@10.0.1.50 -i ~/.ssh/api_key.pem",
    "testingInfo": "npm test && npm run integration-test",
    "database": "postgres://localhost:5432/ecommerce_dev",
    "apiDocs": "http://localhost:3001/api-docs"
  }
}
```

**DevOps Infrastructure:**
```json
{
  "name": "AWS Infrastructure",
  "summary": "Terraform-managed AWS infrastructure for e-commerce platform",
  "tags": ["devops", "aws", "terraform", "infrastructure"],
  "metadata": {
    "connectionInfo": "aws-vault exec production -- terraform plan",
    "testingInfo": "terraform validate && tflint",
    "awsRegion": "us-east-1",
    "stateBackend": "s3://mycompany-terraform-state/ecommerce"
  }
}
```

## Example 2: Research & Development

**ML Model Development:**
```json
{
  "name": "Customer Segmentation ML Model",
  "summary": "scikit-learn model for customer behavior clustering",
  "tags": ["ml", "python", "research", "data-science"],
  "metadata": {
    "connectionInfo": "jupyter lab --port=8888",
    "testingInfo": "pytest tests/ --cov=models",
    "dataSource": "s3://ml-datasets/customer-data/",
    "modelVersion": "v2.1",
    "accuracy": "87%",
    "notebookPath": "notebooks/customer_segmentation.ipynb"
  }
}
```

## Example 3: Bug Investigation

**Critical Bug Workstream:**
```json
{
  "name": "Payment Gateway Timeout Issue",
  "summary": "Investigating intermittent timeouts in Stripe payment processing",
  "tags": ["bug", "critical", "payments", "stripe"],
  "metadata": {
    "connectionInfo": "ssh prod-api-01.internal -L 9229:localhost:9229 (for debugging)",
    "testingInfo": "curl -X POST http://localhost:3001/api/checkout -d @test_payload.json",
    "logFiles": "/var/log/api/payment-gateway.log",
    "relatedTickets": "JIRA-1234, JIRA-1235",
    "rootCause": "Connection pool exhaustion during peak traffic"
  }
}
```

## Example 4: Learning New Technology

**Learning Project:**
```json
{
  "name": "Rust Web Service Learning",
  "summary": "Building a REST API with Actix-web to learn Rust",
  "tags": ["learning", "rust", "actix", "api"],
  "metadata": {
    "connectionInfo": "cargo run --release",
    "testingInfo": "cargo test && cargo clippy",
    "resources": [
      "https://actix.rs/docs/",
      "https://doc.rust-lang.org/book/"
    ],
    "progress": "Completed: routing, middleware. Next: database integration"
  }
}
```

## Example 5: Organizing by Phase

You can create workstreams for different phases of a project:

**Phase 1: Planning**
```json
{
  "name": "Mobile App - Planning Phase",
  "summary": "Requirements gathering and architecture design for iOS/Android app",
  "tags": ["mobile", "planning", "phase-1"],
  "metadata": {
    "figmaDesigns": "https://figma.com/file/abc123",
    "architectureDocs": "https://notion.so/arch-design-doc",
    "stakeholders": "john@company.com, jane@company.com"
  }
}
```

**Phase 2: Development**
```json
{
  "name": "Mobile App - Development Phase",
  "summary": "React Native development sprint",
  "tags": ["mobile", "development", "phase-2", "react-native"],
  "metadata": {
    "hostIps": ["localhost:8081"],
    "connectionInfo": "npx react-native start",
    "testingInfo": "npm test && detox test",
    "targetRelease": "2026-02-15"
  }
}
```

## Searching and Filtering

### Find all production-related work:
```json
{
  "tags": ["production"],
  "matchAll": false
}
```

### Find work that requires both frontend and testing:
```json
{
  "tags": ["frontend", "testing"],
  "matchAll": true
}
```

### Search by text:
```json
{
  "query": "payment"
}
```

## Best Practices

### 1. Consistent Tagging
Use a standard set of tags across your workstreams:
- **Type**: `frontend`, `backend`, `devops`, `ml`, `mobile`
- **Status**: `planning`, `development`, `testing`, `production`
- **Priority**: `critical`, `high`, `normal`, `low`
- **Technology**: `python`, `nodejs`, `rust`, `react`, etc.

### 2. Rich Metadata
Always include:
- **hostIps**: Where the service runs
- **connectionInfo**: How to connect/start the service
- **testingInfo**: How to run tests
- **Additional context**: Anything that helps you context-switch quickly

### 3. Regular Updates
Update workstreams as you learn new information:
```json
{
  "id": "ws-existing-id",
  "metadata": {
    "deployedVersion": "v1.2.3",
    "lastDeployed": "2026-01-16",
    "knownIssues": "Memory leak in background worker, investigating"
  }
}
```

### 4. Use Descriptive Names and Summaries
- **Good**: "Customer API - Authentication Service"
- **Bad**: "API thing"

- **Good Summary**: "OAuth2-based authentication service handling login, registration, and token refresh for customer-facing applications"
- **Bad Summary**: "auth stuff"

## Integration with Your Workflow

### Morning Routine
1. List all workstreams: `list_workstreams`
2. Check high-priority items: `search_by_tags` with `["critical", "high"]`
3. Get detailed info: `get_workstream` for active items

### Context Switching
When switching between projects:
1. Search for the project: `search_workstreams` with project name
2. Review connection info and testing commands
3. Start services using the provided connection info

### End of Day
1. Update progress in workstream metadata
2. Add new tags if status changed (e.g., add "testing" tag)
3. Note any blockers or next steps in metadata

## Advanced: Custom Metadata Fields

You can add any custom fields to metadata:

```json
{
  "name": "Microservice Alpha",
  "summary": "User authentication microservice",
  "tags": ["microservice", "auth"],
  "metadata": {
    "hostIps": ["10.0.1.10"],
    "connectionInfo": "kubectl port-forward svc/auth-service 8080:80",
    "testingInfo": "go test ./... -v",
    
    // Custom fields:
    "k8sNamespace": "production",
    "slackChannel": "#team-auth",
    "oncallRotation": "https://pagerduty.com/schedules/auth-team",
    "runbook": "https://wiki.company.com/runbooks/auth-service",
    "dependencies": ["user-db", "redis-cache", "email-service"],
    "healthcheck": "curl http://localhost:8080/health",
    "metricsUrl": "https://grafana.company.com/d/auth-dashboard"
  }
}
```

This flexibility allows you to tailor local-mem to your specific workflow and organizational needs.
