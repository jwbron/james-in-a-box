#!/usr/bin/env python3
"""Minimal ICAP server for Anthropic API header injection.

ICAP (Internet Content Adaptation Protocol) allows modifying HTTP requests
as they pass through the Squid proxy. This server handles REQMOD (request
modification) to inject authentication headers into api.anthropic.com requests.

This is a minimal implementation supporting only what's needed for credential
injection. It implements RFC 3507 just enough to work with Squid.

Usage:
    python anthropic_icap_server.py [--port 1344] [--host 127.0.0.1]

Protocol Flow:
    1. Squid sends REQMOD request with encapsulated HTTP headers
    2. This server adds the authentication header
    3. Returns modified request to Squid
    4. Squid forwards the modified request to Anthropic
"""

import argparse
import logging
import socket
import sys
import threading
from pathlib import Path


# Add parent directory for imports when running as script
sys.path.insert(0, str(Path(__file__).parent))

from anthropic_credentials import AnthropicCredential, get_credential_cached


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s icap_server %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger(__name__)

# ICAP server configuration
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 1344
ICAP_VERSION = "ICAP/1.0"
SERVICE_NAME = "anthropic-auth"


class ICAPRequest:
    """Parsed ICAP request."""

    def __init__(self):
        self.method: str = ""
        self.uri: str = ""
        self.version: str = ""
        self.headers: dict[str, str] = {}
        self.encapsulated: dict[str, int] = {}
        self.http_request_headers: bytes = b""
        self.http_request_body: bytes = b""


def parse_icap_request(data: bytes) -> ICAPRequest | None:
    """Parse an ICAP request from raw bytes."""
    try:
        # Split headers from body
        if b"\r\n\r\n" not in data:
            return None

        header_end = data.index(b"\r\n\r\n")
        header_section = data[:header_end].decode("utf-8", errors="replace")
        body_section = data[header_end + 4 :]

        lines = header_section.split("\r\n")
        if not lines:
            return None

        # Parse request line: METHOD URI ICAP/1.0
        request_line = lines[0].split(" ")
        if len(request_line) < 3:
            return None

        req = ICAPRequest()
        req.method = request_line[0]
        req.uri = request_line[1]
        req.version = request_line[2]

        # Parse headers
        for line in lines[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                req.headers[key.lower()] = value

        # Parse Encapsulated header to find HTTP request parts
        if "encapsulated" in req.headers:
            # Format: "req-hdr=0, req-body=xxx" or "req-hdr=0, null-body=xxx"
            for part in req.headers["encapsulated"].split(","):
                part = part.strip()
                if "=" in part:
                    name, offset = part.split("=")
                    req.encapsulated[name.strip()] = int(offset)

        # Extract encapsulated HTTP request headers
        if "req-hdr" in req.encapsulated:
            hdr_start = req.encapsulated["req-hdr"]
            # Find end of HTTP headers (either req-body offset or null-body offset)
            hdr_end = len(body_section)
            for key in ["req-body", "null-body"]:
                if key in req.encapsulated:
                    hdr_end = req.encapsulated[key]
                    break
            req.http_request_headers = body_section[hdr_start:hdr_end]

        # Extract HTTP body if present (for req-body, need to handle chunked)
        if "req-body" in req.encapsulated:
            body_start = req.encapsulated["req-body"]
            req.http_request_body = body_section[body_start:]

        return req
    except Exception as e:
        log.error(f"Failed to parse ICAP request: {e}")
        return None


def build_icap_response(
    status: int,
    status_text: str,
    headers: dict[str, str],
    http_headers: bytes | None = None,
    http_body: bytes | None = None,
    body_already_chunked: bool = False,
) -> bytes:
    """Build an ICAP response.

    Args:
        status: ICAP status code
        status_text: ICAP status text
        headers: ICAP response headers
        http_headers: HTTP request headers to encapsulate
        http_body: HTTP request body to encapsulate
        body_already_chunked: If True, http_body is already in chunked format
                              (from Squid) and should be passed through as-is
    """
    response_lines = [f"{ICAP_VERSION} {status} {status_text}"]

    # Build Encapsulated header
    if http_headers is not None:
        offset = 0
        encapsulated_parts = [f"req-hdr={offset}"]
        offset += len(http_headers)
        if http_body:
            encapsulated_parts.append(f"req-body={offset}")
        else:
            encapsulated_parts.append(f"null-body={offset}")
        headers["Encapsulated"] = ", ".join(encapsulated_parts)

    # Add headers
    for key, value in headers.items():
        response_lines.append(f"{key}: {value}")

    response_lines.append("")  # Empty line to end headers
    response = "\r\n".join(response_lines).encode("utf-8")
    response += b"\r\n"

    # Add encapsulated content
    if http_headers is not None:
        response += http_headers
        if http_body:
            if body_already_chunked:
                # Body is already chunked (from Squid), pass through as-is
                response += http_body
            else:
                # Wrap body in chunked encoding
                response += f"{len(http_body):x}\r\n".encode()
                response += http_body
                response += b"\r\n0\r\n\r\n"

    return response


def inject_auth_header(http_headers: bytes, credential: AnthropicCredential) -> bytes:
    """Inject authentication header into HTTP request headers.

    Strips any existing auth headers (x-api-key, Authorization) before
    injecting the real credential. This allows Claude Code to use a
    placeholder API key while the gateway injects OAuth tokens.

    Note on placeholder token format dependency:
    Claude Code validates token formats before accepting them. The placeholder
    tokens in jib_lib/auth.py must match Anthropic's expected patterns:
    - API keys: sk-ant-* prefix (50+ chars)
    - OAuth tokens: sk-ant-oat01-* prefix
    If Anthropic changes their token validation, the placeholders may need
    updating. See jib_lib/auth.py for the current placeholder values.
    """
    # Decode headers
    try:
        headers_str = http_headers.decode("utf-8", errors="replace")
    except Exception:
        return http_headers

    # Split into lines
    lines = headers_str.split("\r\n")
    if not lines:
        return http_headers

    # Headers to strip (case-insensitive comparison)
    headers_to_strip = {"x-api-key", "authorization"}

    # Filter out existing auth headers and insert the real one
    result_lines = []
    auth_inserted = False
    for i, line in enumerate(lines):
        # Check if this is an auth header to strip
        lower_line = line.lower()
        if any(lower_line.startswith(h + ":") for h in headers_to_strip):
            # Skip this header (strip it)
            continue

        if line == "" and i > 0 and not auth_inserted:
            # Insert auth header before the first empty line (end of headers)
            result_lines.append(f"{credential.header_name}: {credential.header_value}")
            auth_inserted = True
        result_lines.append(line)

    return "\r\n".join(result_lines).encode("utf-8")


def handle_options(request: ICAPRequest) -> bytes:
    """Handle ICAP OPTIONS request."""
    headers = {
        "Methods": "REQMOD",
        "Service": "ICAP Anthropic Auth Service",
        "ISTag": '"anthropic-auth-1"',
        "Max-Connections": "100",
        "Options-TTL": "3600",
        "Preview": "0",
        "Transfer-Preview": "*",
        "Allow": "204",
    }
    return build_icap_response(200, "OK", headers)


def handle_reqmod(request: ICAPRequest) -> bytes:
    """Handle ICAP REQMOD request - inject auth header."""
    # Debug: log what body we received and encapsulated header
    body_repr = repr(request.http_request_body[:100]) if request.http_request_body else "None"
    log.info(f"REQMOD encapsulated: {request.encapsulated}, body preview: {body_repr}")

    # Load credential (cached, refreshes on file change)
    credential = get_credential_cached()

    if credential is None:
        log.warning("No valid credentials - returning request unmodified")
        # Return 204 No Content (request not modified)
        return build_icap_response(204, "No Content", {"ISTag": '"anthropic-auth-1"'})

    # Check if this is an Anthropic API request (redundant but safe)
    http_headers = request.http_request_headers
    if b"api.anthropic.com" not in http_headers and b"Host:" in http_headers:
        log.debug("Not an Anthropic request - returning unmodified")
        return build_icap_response(204, "No Content", {"ISTag": '"anthropic-auth-1"'})

    # Inject auth header
    modified_headers = inject_auth_header(http_headers, credential)

    log.debug(f"Injected {credential.header_name} header into request")

    # Build response with modified headers
    headers = {"ISTag": '"anthropic-auth-1"'}

    # Handle body if present - it's already in chunked format from Squid
    http_body = request.http_request_body if request.http_request_body else None

    return build_icap_response(
        200, "OK", headers, modified_headers, http_body, body_already_chunked=True
    )


def is_preview_request(request: ICAPRequest) -> bool:
    """Check if this is a preview request that needs 100 Continue for full body."""
    # If there's a req-body but we only got the chunked terminator, it's a preview
    # Preview body is just "0\r\n\r\n" (5 bytes) - the chunked terminator
    return bool("req-body" in request.encapsulated and request.http_request_body == b"0\r\n\r\n")


def read_icap_data(client_socket: socket.socket, address: tuple) -> bytes:
    """Read ICAP request data from socket until complete."""
    data = b""
    client_socket.settimeout(10.0)

    while True:
        try:
            chunk = client_socket.recv(65536)
            if not chunk:
                log.debug(f"Connection closed by peer {address}")
                break
            data += chunk
            log.debug(f"Read {len(chunk)} bytes, total {len(data)} bytes from {address}")

            # Check for complete request
            if b"\r\n\r\n" in data:
                # For OPTIONS, we're done after headers
                if data.startswith(b"OPTIONS"):
                    break
                # For REQMOD, check if we have all encapsulated content
                data_str = data.decode("utf-8", errors="replace")
                if "null-body=" in data_str:
                    break
                # For chunked body, need to find the terminating 0\r\n\r\n
                if b"0\r\n\r\n" in data:
                    break
        except TimeoutError:
            log.warning(f"Timeout reading from {address} after {len(data)} bytes")
            break

    return data


def handle_client(client_socket: socket.socket, address: tuple) -> None:
    """Handle a single ICAP client connection."""
    try:
        log.info(f"New connection from {address}")

        # Read initial request
        data = read_icap_data(client_socket, address)
        if not data:
            log.info(f"No data received from {address}")
            return

        log.info(f"Received {len(data)} bytes from {address}")

        # Parse request
        request = parse_icap_request(data)
        if request is None:
            log.warning(f"Failed to parse request from {address}")
            response = build_icap_response(400, "Bad Request", {})
            client_socket.sendall(response)
            return

        log.info(f"Parsed {request.method} request from {address}")

        # Route by method
        if request.method == "OPTIONS":
            response = handle_options(request)
        elif request.method == "REQMOD":
            log.info(f"Processing REQMOD, body size: {len(request.http_request_body)} bytes")

            # Check if this is a preview request that needs full body
            if is_preview_request(request):
                log.info("Preview request detected, sending 100 Continue")
                # Send 100 Continue to request full body
                continue_response = f"{ICAP_VERSION} 100 Continue\r\n\r\n".encode()
                client_socket.sendall(continue_response)

                # Read the full body
                log.info("Waiting for full body after 100 Continue")
                body_data = b""
                client_socket.settimeout(10.0)
                while True:
                    try:
                        chunk = client_socket.recv(65536)
                        if not chunk:
                            break
                        body_data += chunk
                        log.debug(f"Body chunk: {len(chunk)} bytes, total {len(body_data)}")
                        # Check for chunked body terminator
                        if b"0\r\n\r\n" in body_data:
                            break
                    except TimeoutError:
                        log.warning(f"Timeout reading body from {address}")
                        break

                log.info(f"Received full body: {len(body_data)} bytes")
                request.http_request_body = body_data

            response = handle_reqmod(request)
        else:
            log.warning(f"Unsupported method: {request.method}")
            response = build_icap_response(405, "Method Not Allowed", {"Allow": "OPTIONS, REQMOD"})

        log.info(f"Sending {len(response)} byte response to {address}")
        client_socket.sendall(response)
        log.info(f"Response sent successfully to {address}")

    except Exception as e:
        log.exception(f"Error handling client {address}: {e}")
    finally:
        client_socket.close()


def run_server(host: str, port: int) -> None:
    """Run the ICAP server."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server.bind((host, port))
        server.listen(10)
        log.info(f"ICAP server listening on {host}:{port}")

        # Verify credentials are available at startup
        credential = get_credential_cached()
        if credential:
            log.info(f"Credential loaded: {credential.header_name}")
        else:
            log.warning("No valid credentials at startup - requests will pass through unmodified")

        while True:
            try:
                client_socket, address = server.accept()
                # Handle each client in a thread
                thread = threading.Thread(
                    target=handle_client, args=(client_socket, address), daemon=True
                )
                thread.start()
            except KeyboardInterrupt:
                log.info("Shutting down ICAP server")
                break
            except Exception as e:
                log.error(f"Error accepting connection: {e}")

    finally:
        server.close()


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(description="ICAP server for Anthropic auth")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Host to listen on")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to listen on")
    args = parser.parse_args()

    run_server(args.host, args.port)


if __name__ == "__main__":
    main()
