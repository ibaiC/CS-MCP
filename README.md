# Cobalt Strike MCP Server

An MCP (Model Context Protocol) server that provides access to Cobalt Strike API operations.

## Features

- **Automatic Authentication**: Authenticates with Cobalt Strike API and manages bearer token
- **Dynamic Tool Generation**: Automatically creates MCP tools from the OpenAPI specification
- **Full API Coverage**: Exposes all Cobalt Strike API operations as MCP tools

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment variables (copy `.env.example` to `.env` and edit):
```bash
cp .env.example .env
```

3. Set your Cobalt Strike credentials:
```bash
export CS_BASE_URL="https://your-cs-server:50443"
export CS_USERNAME="your-username"
export CS_PASSWORD="your-password"
export CS_VERIFY_SSL="false"  # Set to "true" if using valid SSL cert
```

## Usage

### Running the Server

```bash
python server.py
```

### Using with MCP Client

Add to your MCP client configuration (e.g., Claude Desktop):

```json
{
  "mcpServers": {
    "cobalt-strike": {
      "command": "python",
      "args": ["/path/to/CS-MCP/server.py"],
      "env": {
        "CS_BASE_URL": "https://your-cs-server:50443",
        "CS_USERNAME": "your-username",
        "CS_PASSWORD": "your-password",
        "CS_VERIFY_SSL": "false"
      }
    }
  }
}
```

## How It Works

1. **Authentication**: On startup, the server authenticates with `/api/auth/login` and retrieves a bearer token
2. **API Client Initialization**: Creates an HTTP client with the bearer token in the Authorization header
3. **OpenAPI Spec Loading**: Fetches the OpenAPI specification from `/v3/api-docs`
4. **Tool Generation**: Dynamically creates MCP tools for each API operation
5. **Request Handling**: Routes tool calls to the appropriate API endpoints with proper authentication

## Environment Variables

- `CS_BASE_URL`: Base URL of the Cobalt Strike server
- `CS_USERNAME`: Username for authentication (required)
- `CS_PASSWORD`: Password for authentication (required)
- `CS_VERIFY_SSL`: Whether to verify SSL certificates (default: `false`)

## Security Notes

- Store credentials securely (use environment variables, not hardcoded values)
- Consider using SSL certificate verification in production (`CS_VERIFY_SSL=true`)
- The bearer token is managed automatically and refreshed as needed
