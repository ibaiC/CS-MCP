#!/usr/bin/env python3
"""
Cobalt Strike MCP Server
Authenticates with Cobalt Strike API and exposes operations via MCP
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
import mcp.server.stdio


# Configuration - can be set via environment variables
BASE_URL = os.getenv("CS_BASE_URL", "https://10.10.10.10:50443")
USERNAME = os.getenv("CS_USERNAME", "")
PASSWORD = os.getenv("CS_PASSWORD", "")
VERIFY_SSL = os.getenv("CS_VERIFY_SSL", "false").lower() == "true"

# Global variables
bearer_token: Optional[str] = None
api_client: Optional[httpx.AsyncClient] = None
openapi_spec: Optional[Dict[str, Any]] = None


async def authenticate() -> str:
    """
    Authenticate with Cobalt Strike API and retrieve bearer token
    
    Returns:
        str: The access token
    """
    global bearer_token
    
    if not USERNAME or not PASSWORD:
        raise ValueError("CS_USERNAME and CS_PASSWORD environment variables must be set")
    
    login_url = f"{BASE_URL}/api/auth/login"
    login_data = {
        "username": USERNAME,
        "password": PASSWORD
    }
    
    async with httpx.AsyncClient(verify=VERIFY_SSL) as client:
        try:
            response = await client.post(login_url, json=login_data)
            response.raise_for_status()
            
            auth_response = response.json()
            access_token = auth_response.get("access_token")
            
            if not access_token:
                raise ValueError("No access_token in authentication response")
            
            bearer_token = access_token
            print(f"✓ Successfully authenticated with Cobalt Strike API", file=sys.stderr)
            return access_token
            
        except httpx.HTTPError as e:
            raise Exception(f"Authentication failed: {e}")


async def initialize_api_client(token: str) -> httpx.AsyncClient:
    """
    Initialize the API client with bearer token authentication
    
    Args:
        token: The bearer token for authentication
        
    Returns:
        httpx.AsyncClient: Configured API client
    """
    global api_client
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    api_client = httpx.AsyncClient(
        base_url=BASE_URL,
        headers=headers,
        verify=VERIFY_SSL,
        timeout=30.0
    )
    
    print(f"✓ API client initialized with bearer token", file=sys.stderr)
    return api_client


async def fetch_openapi_spec() -> Dict[str, Any]:
    """
    Fetch the OpenAPI specification from the API
    
    Returns:
        Dict: The OpenAPI specification
    """
    global openapi_spec
    
    if not api_client:
        raise Exception("API client not initialized")
    
    spec_url = "/v3/api-docs"
    
    try:
        response = await api_client.get(spec_url)
        response.raise_for_status()
        
        openapi_spec = response.json()
        
        # Count available operations
        operation_count = 0
        if "paths" in openapi_spec:
            for path_data in openapi_spec["paths"].values():
                operation_count += len([k for k in path_data.keys() if k in ["get", "post", "put", "delete", "patch"]])
        
        print(f"✓ Loaded OpenAPI spec with {operation_count} operations", file=sys.stderr)
        return openapi_spec
        
    except httpx.HTTPError as e:
        raise Exception(f"Failed to fetch OpenAPI spec: {e}")


def create_tools_from_openapi() -> list[Tool]:
    """
    Create MCP tools from the OpenAPI specification
    
    Returns:
        list[Tool]: List of MCP tools
    """
    if not openapi_spec or "paths" not in openapi_spec:
        return []
    
    tools = []
    
    for path, path_item in openapi_spec["paths"].items():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method not in path_item:
                continue
            
            operation = path_item[method]
            operation_id = operation.get("operationId", f"{method}_{path.replace('/', '_')}")
            summary = operation.get("summary", "")
            description = operation.get("description", summary)
            
            # Build input schema from parameters and requestBody
            properties = {}
            required = []
            
            # Add path parameters
            if "parameters" in operation:
                for param in operation["parameters"]:
                    param_name = param.get("name")
                    param_schema = param.get("schema", {})
                    properties[param_name] = {
                        "type": param_schema.get("type", "string"),
                        "description": param.get("description", "")
                    }
                    if param.get("required", False):
                        required.append(param_name)
            
            # Add request body if present
            if "requestBody" in operation:
                request_body = operation["requestBody"]
                if "content" in request_body:
                    for content_type, content_data in request_body["content"].items():
                        if "application/json" in content_type and "schema" in content_data:
                            properties["requestBody"] = {
                                "type": "object",
                                "description": "Request body (JSON)"
                            }
                            if request_body.get("required", False):
                                required.append("requestBody")
            
            input_schema = {
                "type": "object",
                "properties": properties
            }
            
            if required:
                input_schema["required"] = required
            
            tool = Tool(
                name=operation_id,
                description=f"{summary}\n\nPath: {method.upper()} {path}\n{description}",
                inputSchema=input_schema
            )
            
            tools.append(tool)
    
    return tools


async def call_api_operation(operation_id: str, arguments: Dict[str, Any]) -> Any:
    """
    Call an API operation based on operation ID and arguments
    
    Args:
        operation_id: The operation ID from OpenAPI spec
        arguments: The arguments for the operation
        
    Returns:
        The API response
    """
    if not api_client or not openapi_spec:
        raise Exception("API client or OpenAPI spec not initialized")
    
    # Find the operation in the spec
    for path, path_item in openapi_spec["paths"].items():
        for method in ["get", "post", "put", "delete", "patch"]:
            if method not in path_item:
                continue
            
            operation = path_item[method]
            if operation.get("operationId") == operation_id:
                # Build the actual path with path parameters
                actual_path = path
                request_params = {}
                request_body = None
                
                # Extract path parameters
                if "parameters" in operation:
                    for param in operation["parameters"]:
                        param_name = param.get("name")
                        param_in = param.get("in")
                        
                        if param_name in arguments:
                            if param_in == "path":
                                actual_path = actual_path.replace(f"{{{param_name}}}", str(arguments[param_name]))
                            elif param_in == "query":
                                request_params[param_name] = arguments[param_name]
                
                # Extract request body
                if "requestBody" in arguments:
                    request_body = arguments["requestBody"]
                
                # Make the API call
                try:
                    if method == "get":
                        response = await api_client.get(actual_path, params=request_params)
                    elif method == "post":
                        response = await api_client.post(actual_path, json=request_body, params=request_params)
                    elif method == "put":
                        response = await api_client.put(actual_path, json=request_body, params=request_params)
                    elif method == "delete":
                        response = await api_client.delete(actual_path, params=request_params)
                    elif method == "patch":
                        response = await api_client.patch(actual_path, json=request_body, params=request_params)
                    
                    response.raise_for_status()
                    
                    # Try to parse as JSON, otherwise return text
                    try:
                        return response.json()
                    except:
                        return response.text
                        
                except httpx.HTTPError as e:
                    raise Exception(f"API call failed: {e}")
    
    raise Exception(f"Operation {operation_id} not found in OpenAPI spec")


async def main():
    """Main entry point for the MCP server"""
    
    print("Starting Cobalt Strike MCP Server...", file=sys.stderr)
    
    # Step 1: Authenticate and get bearer token
    try:
        token = await authenticate()
    except Exception as e:
        print(f"✗ Authentication failed: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Step 2: Initialize API client with bearer token
    try:
        await initialize_api_client(token)
    except Exception as e:
        print(f"✗ Failed to initialize API client: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Step 3: Fetch OpenAPI specification
    try:
        await fetch_openapi_spec()
    except Exception as e:
        print(f"✗ Failed to fetch OpenAPI spec: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Step 4: Create MCP server
    server = Server("cobalt-strike-mcp")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools from the OpenAPI spec"""
        return create_tools_from_openapi()
    
    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Call a tool (API operation)"""
        try:
            result = await call_api_operation(name, arguments or {})
            
            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
                )
            ]
        except Exception as e:
            return [
                TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )
            ]
    
    # Run the server
    print("✓ MCP Server ready", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )




if __name__ == "__main__":
    asyncio.run(main())