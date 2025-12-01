# ADR: Model-Agnostic Architecture for jib

**Driver:** James Wiesebron
**Approver:** TBD
**Contributors:** James Wiesebron, Claude (AI Pair Programming)
**Informed:** Engineering teams
**Proposed:** November 2025
**Status:** Proposed

## Table of Contents

- [Context](#context)
  - [Industry Landscape](#industry-landscape)
  - [Background](#background)
  - [Problem Statement](#problem-statement)
  - [What We're Deciding](#what-were-deciding)
  - [Key Requirements](#key-requirements)
- [Decision](#decision)
- [High-Level Design](#high-level-design)
- [Implementation Details](#implementation-details)
  - [MCP-First Tool Strategy](#8-mcp-first-tool-strategy)
  - [Prompt Normalization Layer](#9-prompt-normalization-layer)
  - [Cross-Model Testing Strategy](#10-cross-model-testing-strategy)
  - [Observability and Cost Tracking](#11-observability-and-cost-tracking)
  - [Extended Capability Matching](#12-extended-capability-matching)
- [Migration Strategy](#migration-strategy)
- [Consequences](#consequences)
- [Decision Permanence](#decision-permanence)
- [Alternatives Considered](#alternatives-considered)

## Context

### Industry Landscape

The LLM ecosystem has matured significantly, with several established patterns for multi-provider abstraction:

- **[LiteLLM](https://github.com/BerriAI/litellm)**: Industry-leading solution supporting 100+ providers with battle-tested routing, fallback, and load balancing
- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)**: Anthropic's provider-agnostic tool protocol, gaining adoption across providers
- **[Vercel AI SDK](https://sdk.vercel.ai/)**: TypeScript-first abstraction for frontend/Node.js applications

These existing solutions inform our architecture decisions and offer integration opportunities.

### Background

**Current State:**

The james-in-a-box (jib) system is tightly coupled to **Claude Code CLI** as its LLM provider:

1. **Direct CLI invocation:** `shared/claude/runner.py` executes `claude --dangerously-skip-permissions`
2. **Claude-specific configuration:** `.claude/rules/` and `.claude/commands/` directories
3. **Hardcoded assumptions:** Scripts assume Claude's tool-use capabilities, context window, and output format
4. **Single model for all tasks:** Same model handles simple analysis and complex code generation

**Coupling Points (Current):**
```
shared/claude/runner.py          → subprocess.run(["claude", ...])
jib-container/.claude/           → Claude Code specific configuration
host-services/*-analyzer.py      → invoke Claude via runner.py
jib-tasks/*-processor.py         → invoke Claude via runner.py
```

### Problem Statement

While Claude is excellent for our use case, tight coupling creates risks and misses optimization opportunities:

1. **Single Point of Failure:** If Anthropic API is down or Claude Code has issues, jib is fully blocked
2. **No Cost Optimization:** Using a frontier model for simple tasks (e.g., formatting, classification) is wasteful
3. **Vendor Lock-in:** Switching providers requires touching dozens of files
4. **Emerging Alternatives:** Other models (GPT-4o, Gemini Pro, open-source) may excel at specific tasks
5. **Latency Sensitivity:** Some workflows need fast responses (smaller models), others need quality (larger models)
6. **Experimental Capability:** Cannot easily test new models without production risk

### What We're Deciding

This ADR proposes architecture to make jib **model-agnostic**, enabling:

1. **Provider abstraction:** Swap between Claude, OpenAI, Google, or local models
2. **Task-based model selection:** Route different workflows to appropriate models
3. **Fallback chains:** If primary model fails, try alternatives
4. **Cost optimization:** Use cheaper models for simple tasks
5. **Experimentation:** A/B test models without code changes

### Key Requirements

**Functional:**
1. Support multiple LLM providers (Anthropic, OpenAI, Google, local)
2. Allow task-specific model selection via configuration
3. Maintain current capabilities (tool use, file access, context awareness)
4. Enable fallback when primary model unavailable
5. Preserve existing workflows during migration

**Non-Functional:**
1. Minimal performance overhead (<100ms per invocation)
2. No disruption to existing workflows
3. Configuration-driven (no code changes to switch models)
4. Maintain security model (sandboxed execution)
5. Observable (log which model handled which request)

## Decision

**We will implement a provider-agnostic abstraction layer with configuration-driven model selection and task routing.**

### Core Architecture Principles

1. **Provider Interface:** Abstract LLM interaction behind a common interface
2. **Model Registry:** Configuration-based model definitions with capabilities
3. **Task Router:** Map workflow types to appropriate models
4. **Fallback Chain:** Automatic failover between providers
5. **Gradual Migration:** Claude Code remains primary; abstraction enables alternatives

### Decision Matrix

| Decision Area | Chosen Approach | Key Rationale | Rejected Alternatives |
|---------------|-----------------|---------------|----------------------|
| **Abstraction Level** | Provider abstraction with capability matching | Supports diverse APIs while enabling intelligent routing | No abstraction (status quo), Full unification (too complex) |
| **Primary Provider** | Claude Code (unchanged) | Proven quality, deep integration, tool use | Immediate switch to multi-provider |
| **Configuration** | YAML-based model registry | Human-readable, version-controllable | Environment variables (limited), Database (over-engineered) |
| **Task Routing** | Static config + runtime override | Predictable, auditable, flexible | ML-based routing (complex), No routing (inefficient) |
| **Fallback Strategy** | Chain with exponential backoff | Resilient, prevents cascade failures | No fallback (brittle), Random selection (unpredictable) |
| **Tool Integration** | MCP where available, custom adapters elsewhere | Industry standard, provider-agnostic | Claude-only tools, Custom protocols |
| **Routing Engine** | LiteLLM-based or inspired implementation | Battle-tested, reduces custom code | Fully custom router (reinventing wheel) |
| **Observability** | Integrated with Standardized Logging ADR | Unified cost/performance tracking | Separate logging per provider |

## High-Level Design

### Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           jib Application Layer                           │
│                                                                           │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐   │
│  │ github-processor │  │ jira-processor  │  │ incoming-processor      │   │
│  │ (code review)    │  │ (ticket analysis)│  │ (complex tasks)         │   │
│  └────────┬─────────┘  └────────┬────────┘  └───────────┬─────────────┘   │
│           │                     │                        │                 │
│           └─────────────────────┼────────────────────────┘                 │
│                                 │                                          │
│                                 ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                        Model Router                                   │ │
│  │                                                                       │ │
│  │   ┌─────────────────────────────────────────────────────────────┐    │ │
│  │   │                    Task → Model Mapping                      │    │ │
│  │   │                                                              │    │ │
│  │   │  code_review:        claude-opus-4 > gpt-4o > claude-sonnet  │    │ │
│  │   │  ticket_analysis:    claude-sonnet > gpt-4o-mini             │    │ │
│  │   │  simple_classification: gpt-4o-mini > claude-haiku           │    │ │
│  │   │  complex_reasoning:  claude-opus-4 > gpt-4o                  │    │ │
│  │   └─────────────────────────────────────────────────────────────┘    │ │
│  └────────────────────────────────────────────────────────────────────┬─┘ │
└───────────────────────────────────────────────────────────────────────┼───┘
                                                                        │
                                                                        ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                          Provider Abstraction Layer                         │
│                                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │ Claude Code  │  │ OpenAI       │  │ Google       │  │ Local/       │   │
│  │ Provider     │  │ Provider     │  │ Provider     │  │ Ollama       │   │
│  │              │  │              │  │              │  │ Provider     │   │
│  │ - CLI        │  │ - API        │  │ - API        │  │ - API        │   │
│  │ - MCP tools  │  │ - Functions  │  │ - Functions  │  │ - Ollama API │   │
│  │ - Native     │  │ - MCP (beta) │  │ - Vertex AI  │  │ - MCP        │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │
│         │                 │                 │                  │           │
└─────────┼─────────────────┼─────────────────┼──────────────────┼───────────┘
          │                 │                 │                  │
          ▼                 ▼                 ▼                  ▼
    Claude API        OpenAI API       Google AI API       Local Model
```

### Component Responsibilities

**1. Model Router**
- Receives task requests from application layer
- Looks up task → model mapping from configuration
- Selects appropriate provider based on availability and capability
- Implements fallback logic when primary model unavailable
- Emits observability events (which model handled which request)

**2. Provider Abstraction Layer**
- Common interface for all LLM providers
- Handles authentication, rate limiting, retries
- Normalizes request/response formats
- Adapts tool use protocols (MCP, function calling, etc.)
- Reports capability metadata (context window, tool support, etc.)

**3. Model Registry (Configuration)**
- YAML-based definitions of available models
- Capability metadata (tools, context, latency, cost)
- Task → model routing rules
- Fallback chain definitions
- Environment-specific overrides (dev vs. prod)

### Data Flow

```
Task Request (e.g., "review this PR")
         │
         ▼
    ┌─────────────────────────┐
    │    Model Router          │
    │                          │
    │ 1. Identify task type    │
    │ 2. Look up model chain   │
    │ 3. Check availability    │
    │ 4. Select provider       │
    └────────────┬─────────────┘
                 │
                 ▼
    ┌─────────────────────────┐
    │  Provider Abstraction    │
    │                          │
    │ 1. Adapt prompt format   │
    │ 2. Configure tools       │
    │ 3. Execute request       │
    │ 4. Normalize response    │
    └────────────┬─────────────┘
                 │
                 ▼
         LLM API Call
                 │
                 ▼
    ┌─────────────────────────┐
    │  Response Processing     │
    │                          │
    │ 1. Parse response        │
    │ 2. Execute tool calls    │
    │ 3. Return result         │
    └─────────────────────────┘
```

## Implementation Details

### 1. Provider Interface

```python
# shared/llm/provider.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ToolCapability(Enum):
    """Capabilities a provider may support."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    CODE_EXECUTION = "code_execution"
    WEB_SEARCH = "web_search"
    MCP_TOOLS = "mcp_tools"


@dataclass
class ModelCapabilities:
    """Metadata about a model's capabilities."""
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    tool_capabilities: list[ToolCapability]
    supports_vision: bool
    supports_streaming: bool
    cost_per_1k_input: float  # USD
    cost_per_1k_output: float  # USD
    typical_latency_ms: int


@dataclass
class LLMRequest:
    """Normalized request format."""
    prompt: str
    system_prompt: str | None = None
    tools: list[dict] | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    task_type: str | None = None  # For routing decisions


@dataclass
class LLMResponse:
    """Normalized response format."""
    content: str
    tool_calls: list[dict] | None = None
    model_used: str
    provider: str
    usage: dict[str, int]  # input_tokens, output_tokens
    latency_ms: int
    success: bool
    error: str | None = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openai')."""
        pass

    @abstractmethod
    def get_capabilities(self, model: str) -> ModelCapabilities:
        """Return capabilities for a specific model."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is currently available."""
        pass

    @abstractmethod
    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        """Execute a completion request."""
        pass

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """Check if this provider supports the given model."""
        pass
```

### 2. Claude Code Provider (Primary)

```python
# shared/llm/providers/claude_code.py

import subprocess
from pathlib import Path

from ..provider import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelCapabilities,
    ToolCapability,
)


class ClaudeCodeProvider(LLMProvider):
    """Provider for Claude Code CLI."""

    SUPPORTED_MODELS = {
        "claude-opus-4": "claude-opus-4-20250514",
        "claude-sonnet-4": "claude-sonnet-4-20250514",
        "claude-sonnet-3.5": "claude-3-5-sonnet-20241022",
        "claude-haiku": "claude-3-haiku-20240307",
    }

    @property
    def name(self) -> str:
        return "claude-code"

    def get_capabilities(self, model: str) -> ModelCapabilities:
        # Model-specific capabilities
        capabilities = {
            "claude-opus-4": ModelCapabilities(
                context_window=200000,
                max_output_tokens=32000,
                supports_tools=True,
                tool_capabilities=[
                    ToolCapability.FILE_READ,
                    ToolCapability.FILE_WRITE,
                    ToolCapability.CODE_EXECUTION,
                    ToolCapability.MCP_TOOLS,
                ],
                supports_vision=True,
                supports_streaming=True,
                cost_per_1k_input=0.015,
                cost_per_1k_output=0.075,
                typical_latency_ms=3000,
            ),
            # ... other models
        }
        return capabilities.get(model, capabilities["claude-sonnet-4"])

    def is_available(self) -> bool:
        """Check if Claude CLI is available."""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        """Run Claude Code with the request."""
        import time

        start = time.time()

        # Build prompt with system context if provided
        full_prompt = request.prompt
        if request.system_prompt:
            full_prompt = f"{request.system_prompt}\n\n{request.prompt}"

        try:
            # Use model selection flag when supported
            cmd = ["claude", "--dangerously-skip-permissions"]
            if model in self.SUPPORTED_MODELS:
                cmd.extend(["--model", self.SUPPORTED_MODELS[model]])

            result = subprocess.run(
                cmd,
                input=full_prompt,
                text=True,
                capture_output=True,
                timeout=request.max_tokens or 300,
            )

            latency = int((time.time() - start) * 1000)

            return LLMResponse(
                content=result.stdout,
                tool_calls=None,  # Tool calls handled internally by Claude Code
                model_used=model,
                provider=self.name,
                usage={"input_tokens": 0, "output_tokens": 0},  # Not exposed by CLI
                latency_ms=latency,
                success=result.returncode == 0,
                error=result.stderr if result.returncode != 0 else None,
            )

        except subprocess.TimeoutExpired:
            return LLMResponse(
                content="",
                tool_calls=None,
                model_used=model,
                provider=self.name,
                usage={},
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error="Request timed out",
            )

    def supports_model(self, model: str) -> bool:
        return model in self.SUPPORTED_MODELS
```

### 3. OpenAI Provider (Alternative)

```python
# shared/llm/providers/openai_provider.py

import os
from typing import Any

from ..provider import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ModelCapabilities,
    ToolCapability,
)


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI API."""

    SUPPORTED_MODELS = {
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        "gpt-4-turbo": "gpt-4-turbo",
        "o1": "o1",
        "o1-mini": "o1-mini",
    }

    def __init__(self):
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return self._client

    def get_capabilities(self, model: str) -> ModelCapabilities:
        capabilities = {
            "gpt-4o": ModelCapabilities(
                context_window=128000,
                max_output_tokens=16384,
                supports_tools=True,
                tool_capabilities=[ToolCapability.WEB_SEARCH],
                supports_vision=True,
                supports_streaming=True,
                cost_per_1k_input=0.0025,
                cost_per_1k_output=0.010,
                typical_latency_ms=2000,
            ),
            "gpt-4o-mini": ModelCapabilities(
                context_window=128000,
                max_output_tokens=16384,
                supports_tools=True,
                tool_capabilities=[],
                supports_vision=True,
                supports_streaming=True,
                cost_per_1k_input=0.00015,
                cost_per_1k_output=0.0006,
                typical_latency_ms=1000,
            ),
        }
        return capabilities.get(model, capabilities["gpt-4o"])

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    async def complete(self, request: LLMRequest, model: str) -> LLMResponse:
        import time

        start = time.time()
        client = self._get_client()

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        try:
            response = client.chat.completions.create(
                model=self.SUPPORTED_MODELS.get(model, model),
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=request.tools if request.tools else None,
            )

            latency = int((time.time() - start) * 1000)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                tool_calls=self._parse_tool_calls(response.choices[0].message),
                model_used=model,
                provider=self.name,
                usage={
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                },
                latency_ms=latency,
                success=True,
                error=None,
            )

        except Exception as e:
            return LLMResponse(
                content="",
                tool_calls=None,
                model_used=model,
                provider=self.name,
                usage={},
                latency_ms=int((time.time() - start) * 1000),
                success=False,
                error=str(e),
            )

    def supports_model(self, model: str) -> bool:
        return model in self.SUPPORTED_MODELS

    def _parse_tool_calls(self, message: Any) -> list[dict] | None:
        if not message.tool_calls:
            return None
        return [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in message.tool_calls
        ]
```

### 4. Model Registry Configuration

```yaml
# config/models.yaml

# Model definitions with capabilities
models:
  # Anthropic Claude models (via Claude Code)
  claude-opus-4:
    provider: claude-code
    model_id: claude-opus-4-20250514
    context_window: 200000
    max_output_tokens: 32000
    cost_tier: high
    capabilities:
      - code_generation
      - code_review
      - complex_reasoning
      - tool_use
      - file_operations
    strengths:
      - "Complex multi-step reasoning"
      - "Large codebase understanding"
      - "Nuanced code review"

  claude-sonnet-4:
    provider: claude-code
    model_id: claude-sonnet-4-20250514
    context_window: 200000
    max_output_tokens: 32000
    cost_tier: medium
    capabilities:
      - code_generation
      - code_review
      - tool_use
      - file_operations
    strengths:
      - "Balanced speed and quality"
      - "General-purpose coding"
      - "Good for iterative work"

  claude-haiku:
    provider: claude-code
    model_id: claude-3-haiku-20240307
    context_window: 200000
    max_output_tokens: 4096
    cost_tier: low
    capabilities:
      - simple_analysis
      - classification
      - formatting
    strengths:
      - "Fast responses"
      - "Simple tasks"
      - "Cost-effective"

  # OpenAI models (via API)
  gpt-4o:
    provider: openai
    model_id: gpt-4o
    context_window: 128000
    max_output_tokens: 16384
    cost_tier: medium
    capabilities:
      - code_generation
      - code_review
      - complex_reasoning
    strengths:
      - "Strong general reasoning"
      - "Good with structured output"

  gpt-4o-mini:
    provider: openai
    model_id: gpt-4o-mini
    context_window: 128000
    max_output_tokens: 16384
    cost_tier: very_low
    capabilities:
      - simple_analysis
      - classification
      - formatting
    strengths:
      - "Extremely fast"
      - "Very cheap"
      - "Good for high-volume simple tasks"

  # Google models (via Vertex AI)
  gemini-pro:
    provider: google
    model_id: gemini-1.5-pro
    context_window: 1000000
    max_output_tokens: 8192
    cost_tier: medium
    capabilities:
      - code_generation
      - complex_reasoning
    strengths:
      - "Massive context window"
      - "Good for large codebases"

  # Local models (via Ollama)
  llama-3.2:
    provider: ollama
    model_id: llama3.2:latest
    context_window: 128000
    max_output_tokens: 4096
    cost_tier: free
    capabilities:
      - simple_analysis
      - classification
    strengths:
      - "No API costs"
      - "Privacy (local execution)"
      - "Offline capable"

# Task routing configuration
task_routing:
  # Complex code tasks
  code_review:
    primary: claude-opus-4
    fallback:
      - gpt-4o
      - claude-sonnet-4
    required_capabilities:
      - code_review

  code_generation:
    primary: claude-sonnet-4
    fallback:
      - gpt-4o
      - claude-opus-4
    required_capabilities:
      - code_generation
      - tool_use

  # Analysis tasks
  ticket_analysis:
    primary: claude-sonnet-4
    fallback:
      - gpt-4o
      - gpt-4o-mini
    required_capabilities:
      - simple_analysis

  pr_description:
    primary: claude-sonnet-4
    fallback:
      - gpt-4o
    required_capabilities:
      - code_generation

  # Simple tasks (optimize for cost/speed)
  classification:
    primary: gpt-4o-mini
    fallback:
      - claude-haiku
      - llama-3.2
    required_capabilities:
      - classification

  formatting:
    primary: gpt-4o-mini
    fallback:
      - claude-haiku
    required_capabilities:
      - formatting

  # Complex reasoning (optimize for quality)
  complex_reasoning:
    primary: claude-opus-4
    fallback:
      - gpt-4o
      - gemini-pro
    required_capabilities:
      - complex_reasoning

  # Interactive chat (balance speed and quality)
  interactive:
    primary: claude-code  # Full Claude Code experience
    fallback:
      - claude-sonnet-4
    required_capabilities:
      - tool_use
      - file_operations

# Provider configuration
providers:
  claude-code:
    type: cli
    command: claude
    requires_auth: true
    auth_env: ANTHROPIC_API_KEY

  openai:
    type: api
    base_url: https://api.openai.com/v1
    requires_auth: true
    auth_env: OPENAI_API_KEY

  google:
    type: api
    base_url: https://generativelanguage.googleapis.com/v1
    requires_auth: true
    auth_env: GOOGLE_API_KEY

  ollama:
    type: api
    base_url: http://localhost:11434
    requires_auth: false

# Fallback configuration
fallback:
  max_retries: 3
  backoff_base_ms: 1000
  backoff_multiplier: 2
  max_backoff_ms: 30000

# Environment overrides
environments:
  development:
    # In dev, prefer local models for cost savings
    task_routing:
      classification:
        primary: llama-3.2
        fallback:
          - gpt-4o-mini

  production:
    # In prod, prioritize quality and reliability
    task_routing:
      classification:
        primary: gpt-4o-mini
        fallback:
          - claude-haiku
```

### 5. Model Router

```python
# shared/llm/router.py

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .provider import LLMProvider, LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Record of how a request was routed."""
    task_type: str
    selected_model: str
    selected_provider: str
    fallback_used: bool
    fallback_reason: str | None
    attempts: list[dict]


class ModelRouter:
    """Routes requests to appropriate models based on task type and availability."""

    def __init__(self, config_path: Path | str = "config/models.yaml"):
        self.config = self._load_config(config_path)
        self.providers: dict[str, LLMProvider] = {}
        self._initialize_providers()

    def _load_config(self, path: Path | str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def _initialize_providers(self) -> None:
        """Initialize available providers."""
        from .providers.claude_code import ClaudeCodeProvider
        from .providers.openai_provider import OpenAIProvider
        # Import other providers as needed

        provider_classes = {
            "claude-code": ClaudeCodeProvider,
            "openai": OpenAIProvider,
            # Add more providers
        }

        for provider_name, provider_class in provider_classes.items():
            try:
                provider = provider_class()
                if provider.is_available():
                    self.providers[provider_name] = provider
                    logger.info(f"Initialized provider: {provider_name}")
                else:
                    logger.warning(f"Provider not available: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to initialize {provider_name}: {e}")

    def get_model_for_task(self, task_type: str) -> tuple[str, str]:
        """Get the primary model and provider for a task type.

        Returns:
            Tuple of (model_name, provider_name)
        """
        routing = self.config.get("task_routing", {}).get(task_type)
        if not routing:
            # Default to primary Claude model
            return ("claude-sonnet-4", "claude-code")

        primary = routing["primary"]
        model_config = self.config["models"].get(primary)
        if model_config:
            provider = model_config["provider"]
            if provider in self.providers:
                return (primary, provider)

        # Try fallbacks
        for fallback in routing.get("fallback", []):
            model_config = self.config["models"].get(fallback)
            if model_config:
                provider = model_config["provider"]
                if provider in self.providers:
                    return (fallback, provider)

        raise ValueError(f"No available model for task type: {task_type}")

    async def route(
        self,
        request: LLMRequest,
        task_type: str | None = None,
    ) -> tuple[LLMResponse, RoutingDecision]:
        """Route a request to the appropriate model.

        Args:
            request: The LLM request
            task_type: Override task type (otherwise uses request.task_type)

        Returns:
            Tuple of (response, routing_decision)
        """
        task = task_type or request.task_type or "interactive"
        routing = self.config.get("task_routing", {}).get(task, {})

        model_chain = [routing.get("primary")] + routing.get("fallback", [])
        model_chain = [m for m in model_chain if m]  # Remove None

        if not model_chain:
            model_chain = ["claude-sonnet-4"]  # Default

        attempts = []
        fallback_config = self.config.get("fallback", {})

        for i, model_name in enumerate(model_chain):
            model_config = self.config["models"].get(model_name)
            if not model_config:
                continue

            provider_name = model_config["provider"]
            provider = self.providers.get(provider_name)
            if not provider:
                attempts.append({
                    "model": model_name,
                    "provider": provider_name,
                    "error": "Provider not available",
                })
                continue

            # Calculate backoff for retries
            backoff_ms = min(
                fallback_config.get("backoff_base_ms", 1000) *
                (fallback_config.get("backoff_multiplier", 2) ** i),
                fallback_config.get("max_backoff_ms", 30000),
            )

            if i > 0:
                time.sleep(backoff_ms / 1000)

            try:
                response = await provider.complete(request, model_name)

                decision = RoutingDecision(
                    task_type=task,
                    selected_model=model_name,
                    selected_provider=provider_name,
                    fallback_used=i > 0,
                    fallback_reason=attempts[-1]["error"] if attempts else None,
                    attempts=attempts,
                )

                if response.success:
                    logger.info(
                        f"Request routed: task={task}, model={model_name}, "
                        f"fallback_used={i > 0}"
                    )
                    return response, decision

                attempts.append({
                    "model": model_name,
                    "provider": provider_name,
                    "error": response.error,
                })

            except Exception as e:
                attempts.append({
                    "model": model_name,
                    "provider": provider_name,
                    "error": str(e),
                })

        # All attempts failed
        return (
            LLMResponse(
                content="",
                tool_calls=None,
                model_used=model_chain[-1] if model_chain else "unknown",
                provider="none",
                usage={},
                latency_ms=0,
                success=False,
                error=f"All models failed: {attempts}",
            ),
            RoutingDecision(
                task_type=task,
                selected_model="none",
                selected_provider="none",
                fallback_used=True,
                fallback_reason="All models exhausted",
                attempts=attempts,
            ),
        )
```

### 6. Integration with Existing Code

**Before (Current):**
```python
# jib-tasks/github/github-processor.py
from shared.claude.runner import run_claude

result = run_claude(
    prompt="Review this PR...",
    timeout=600,
    cwd=repo_path,
)
```

**After (Model-Agnostic):**
```python
# jib-tasks/github/github-processor.py
from shared.llm import get_router, LLMRequest

router = get_router()

response, decision = await router.route(
    LLMRequest(
        prompt="Review this PR...",
        task_type="code_review",
    ),
)

# Log routing decision for observability
logger.info(f"Used {decision.selected_model} via {decision.selected_provider}")
```

### 7. Tool Abstraction for Non-Claude Providers

When using providers other than Claude Code, we need to handle tool execution differently:

```python
# shared/llm/tools/adapter.py

from abc import ABC, abstractmethod
from typing import Any


class ToolAdapter(ABC):
    """Adapts tool execution for different providers."""

    @abstractmethod
    def format_tools(self, tools: list[dict]) -> Any:
        """Format tools for the provider's expected format."""
        pass

    @abstractmethod
    def parse_tool_calls(self, response: Any) -> list[dict]:
        """Parse tool calls from provider response."""
        pass

    @abstractmethod
    async def execute_tool(self, tool_call: dict) -> Any:
        """Execute a tool call and return result."""
        pass


class MCPToolAdapter(ToolAdapter):
    """Adapter for MCP-compatible tools."""

    def __init__(self, mcp_servers: dict[str, str]):
        self.mcp_servers = mcp_servers

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """Convert MCP tool definitions to provider format."""
        # MCP tools are already in a standard format
        return tools

    def parse_tool_calls(self, response: Any) -> list[dict]:
        """Parse tool calls from response."""
        # Implementation depends on provider
        pass

    async def execute_tool(self, tool_call: dict) -> Any:
        """Execute tool via MCP server."""
        server = self._get_server_for_tool(tool_call["name"])
        # Execute via MCP protocol
        pass


class OpenAIFunctionAdapter(ToolAdapter):
    """Adapter for OpenAI function calling."""

    def format_tools(self, tools: list[dict]) -> list[dict]:
        """Convert to OpenAI function format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {}),
                },
            }
            for tool in tools
        ]
```

### 8. MCP-First Tool Strategy

The **Model Context Protocol (MCP)** is becoming the industry standard for provider-agnostic tool interaction. Our tool abstraction should prioritize MCP:

**Strategy:**

1. **MCP as primary**: All new tools should be implemented as MCP servers
2. **Fallback adapters**: Use function-calling adapters only for providers without MCP support
3. **Tool registry**: Centralized registry of available MCP servers and their capabilities

```python
# shared/llm/tools/mcp_registry.py

from dataclasses import dataclass

@dataclass
class MCPServer:
    """MCP server configuration."""
    name: str
    url: str
    tools: list[str]
    supports_streaming: bool = True

class MCPToolRegistry:
    """Registry of MCP servers and their tools."""

    def __init__(self):
        self.servers: dict[str, MCPServer] = {}
        self._tool_to_server: dict[str, str] = {}

    def register_server(self, server: MCPServer) -> None:
        """Register an MCP server."""
        self.servers[server.name] = server
        for tool in server.tools:
            self._tool_to_server[tool] = server.name

    def get_server_for_tool(self, tool_name: str) -> MCPServer | None:
        """Find which server provides a tool."""
        server_name = self._tool_to_server.get(tool_name)
        return self.servers.get(server_name) if server_name else None

    def get_all_tools(self) -> list[dict]:
        """Get all available tools for provider negotiation."""
        tools = []
        for server in self.servers.values():
            # Fetch tool schemas from MCP server
            tools.extend(self._fetch_tool_schemas(server))
        return tools
```

**Benefits of MCP-first approach:**
- Provider-agnostic by design
- OpenAI, Google, and others are adding MCP support
- Reduces custom adapter code as ecosystem matures
- Single protocol for all tool interactions

### 9. Prompt Normalization Layer

Different models respond differently to the same prompts. A normalization layer helps maintain consistency:

```python
# shared/llm/prompts/normalizer.py

from dataclasses import dataclass
from typing import Callable


@dataclass
class PromptTemplate:
    """Template with provider-specific variations."""
    base: str
    variations: dict[str, str]  # provider -> modified prompt


class PromptNormalizer:
    """Adapts prompts for different providers."""

    # Known provider quirks
    PROVIDER_ADJUSTMENTS: dict[str, Callable[[str], str]] = {
        "openai": lambda p: p,  # OpenAI works well with standard prompts
        "claude-code": lambda p: p,  # Claude Code handles prompts natively
        "google": lambda p: p.replace("```", "```\n"),  # Gemini prefers newlines
    }

    def __init__(self):
        self.templates: dict[str, PromptTemplate] = {}

    def normalize(self, prompt: str, provider: str) -> str:
        """Adjust prompt for provider-specific behavior."""
        adjuster = self.PROVIDER_ADJUSTMENTS.get(provider, lambda p: p)
        return adjuster(prompt)

    def get_template(self, name: str, provider: str) -> str:
        """Get a named template, with provider variation if available."""
        template = self.templates.get(name)
        if not template:
            raise ValueError(f"Unknown template: {name}")
        return template.variations.get(provider, template.base)
```

**Considerations:**
- Start with minimal normalization; add rules based on observed differences
- Log when normalization is applied for debugging
- Consider A/B testing prompts across providers

### 10. Cross-Model Testing Strategy

Different models behave differently with the same prompts. Rigorous testing across providers is critical:

**Testing Layers:**

1. **Unit Tests**: Mock providers, test routing logic
2. **Integration Tests**: Real API calls with test prompts
3. **Regression Tests**: Golden output comparisons across models
4. **Quality Benchmarks**: Periodic evaluation of model outputs

```python
# tests/llm/test_cross_model.py

import pytest
from shared.llm import get_router, LLMRequest

# Test prompts with expected behaviors
TEST_CASES = [
    {
        "name": "simple_classification",
        "prompt": "Classify this as bug/feature/question: 'The button is blue instead of green'",
        "expected_pattern": r"(bug|Bug|BUG)",
        "task_type": "classification",
    },
    {
        "name": "code_review_basics",
        "prompt": "Review this code: def add(a,b): return a+b",
        "expected_pattern": r"(type hint|docstring|documentation)",
        "task_type": "code_review",
    },
]

@pytest.mark.parametrize("provider", ["claude-code", "openai", "google"])
@pytest.mark.parametrize("test_case", TEST_CASES)
async def test_cross_model_consistency(provider, test_case):
    """Verify consistent behavior across providers."""
    router = get_router()

    # Force specific provider for test
    response, decision = await router.route(
        LLMRequest(
            prompt=test_case["prompt"],
            task_type=test_case["task_type"],
        ),
        force_provider=provider,
    )

    assert response.success
    assert re.search(test_case["expected_pattern"], response.content)
```

**Testing Best Practices:**
- Run cross-model tests before switching primary providers
- Track output quality metrics over time
- Alert on significant quality degradation
- Maintain provider-specific prompt variations when needed

### 11. Observability and Cost Tracking

Integrated observability is critical for multi-provider systems. This integrates with the [Standardized Logging ADR](../in-progress/ADR-Standardized-Logging-Interface.md):

```python
# shared/llm/observability.py

import logging
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LLMInvocationMetrics:
    """Metrics for a single LLM invocation."""
    timestamp: datetime
    task_type: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    success: bool
    fallback_used: bool
    error: str | None = None


class LLMObserver:
    """Observability for LLM invocations."""

    def __init__(self):
        self.logger = logging.getLogger("llm.metrics")

    def record(self, metrics: LLMInvocationMetrics) -> None:
        """Record metrics for an LLM invocation."""
        self.logger.info(
            "llm_invocation",
            extra={
                "task_type": metrics.task_type,
                "model": metrics.model,
                "provider": metrics.provider,
                "input_tokens": metrics.input_tokens,
                "output_tokens": metrics.output_tokens,
                "latency_ms": metrics.latency_ms,
                "cost_usd": metrics.cost_usd,
                "success": metrics.success,
                "fallback_used": metrics.fallback_used,
                "error": metrics.error,
            },
        )

    def get_cost_summary(self, since: datetime) -> dict:
        """Get cost summary by provider and task type."""
        # Implementation would query log aggregation system
        pass
```

**Key Observability Requirements:**

| Metric | Purpose | Alert Threshold |
|--------|---------|-----------------|
| Cost per task type | Budget tracking | >$X/day per type |
| Fallback rate | Provider health | >10% fallbacks |
| Latency p95 | Performance | >5000ms |
| Error rate | Reliability | >5% errors |
| Token efficiency | Optimization | Tokens per task trending up |

**Budget Controls:**
```yaml
# config/models.yaml (addition)
budget:
  daily_limit_usd: 100
  per_task_limits:
    code_review: 1.00
    classification: 0.10
  alerts:
    - threshold: 0.8  # 80% of daily limit
      action: notify
    - threshold: 1.0  # 100% of limit
      action: downgrade_models  # Switch to cheaper alternatives
```

### 12. Extended Capability Matching

Beyond basic capabilities, track operational metrics for intelligent routing:

```python
# shared/llm/capabilities.py

from dataclasses import dataclass


@dataclass
class ExtendedModelCapabilities:
    """Extended capability metrics for intelligent routing."""

    # Basic capabilities
    context_window: int
    max_output_tokens: int
    supports_tools: bool
    supports_vision: bool

    # Operational metrics (updated from observability data)
    token_efficiency: dict[str, float]  # task_type -> avg tokens used
    latency_percentiles: dict[str, int]  # p50, p95, p99 in ms
    error_rate_7d: float  # Rolling 7-day error rate
    cost_per_success: dict[str, float]  # task_type -> avg cost

    # Quality metrics (from evaluation benchmarks)
    quality_scores: dict[str, float]  # task_type -> quality score


def select_optimal_model(
    task_type: str,
    models: list[ExtendedModelCapabilities],
    optimization_target: str = "cost",  # cost, latency, quality
) -> str:
    """Select optimal model based on historical performance."""

    if optimization_target == "cost":
        # Choose model with lowest cost_per_success for this task
        return min(models, key=lambda m: m.cost_per_success.get(task_type, float('inf')))
    elif optimization_target == "latency":
        # Choose model with lowest p95 latency
        return min(models, key=lambda m: m.latency_percentiles.get("p95", float('inf')))
    elif optimization_target == "quality":
        # Choose model with highest quality score
        return max(models, key=lambda m: m.quality_scores.get(task_type, 0))
```

## Migration Strategy

### Phase 1: Abstraction Layer (No Behavior Change)

**Goal:** Build abstraction without changing behavior; Claude Code remains only provider

1. Implement `LLMProvider` interface and `ClaudeCodeProvider`
2. Create `ModelRouter` with Claude-only configuration
3. Add `config/models.yaml` with Claude models only
4. Update `shared/claude/runner.py` to use new abstraction internally
5. All existing code continues working unchanged

**Success Criteria:**
- All existing functionality works identically
- No changes to jib-tasks code required
- Abstraction layer tested with Claude Code

### Phase 2: Add OpenAI as Alternative Provider

**Goal:** Enable OpenAI as fallback for simple tasks

1. Implement `OpenAIProvider`
2. Add OpenAI models to configuration
3. Configure simple tasks (classification, formatting) to use gpt-4o-mini
4. Add observability logging for routing decisions
5. Monitor cost savings and latency improvements

**Success Criteria:**
- Simple tasks routed to gpt-4o-mini successfully
- Fallback to Claude works when OpenAI unavailable
- Measurable cost reduction on high-volume simple tasks

### Phase 3: Task-Based Routing

**Goal:** Intelligent routing based on task requirements

1. Update all processors to specify task types
2. Implement capability matching in router
3. Add routing metrics dashboard
4. Fine-tune task → model mappings based on performance data

**Success Criteria:**
- Each task type routed to optimal model
- A/B testing capability for new model configurations
- Clear visibility into model selection decisions

### Phase 4: Additional Providers

**Goal:** Expand provider options

1. Add Google Gemini provider (massive context window use case)
2. Add Ollama provider for local/offline scenarios
3. Implement provider health checks and auto-failover
4. Add support for custom/self-hosted models

**Success Criteria:**
- Three or more providers available
- Automatic failover tested and working
- Local model option for privacy-sensitive work

## Consequences

### Benefits

1. **Resilience:** Provider outages don't fully block jib
2. **Cost Optimization:** Use cheaper models for simple tasks (potential 50-80% cost reduction)
3. **Flexibility:** Easy to add new models as they emerge
4. **Performance:** Route latency-sensitive tasks to faster models
5. **Experimentation:** A/B test models without code changes
6. **Future-Proofing:** Not locked into single provider
7. **Observability:** Clear visibility into model selection

### Drawbacks

1. **Complexity:** More moving parts to maintain
2. **Configuration Overhead:** Need to tune task→model mappings
3. **Testing Surface:** Must test with multiple providers
4. **Tool Parity:** Non-Claude providers may lack tool capabilities
5. **Prompt Engineering:** Different models may need different prompts

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Different model behaviors cause inconsistent results | Extensive testing, per-model prompt tuning |
| Configuration complexity leads to errors | Strong defaults, validation, gradual rollout |
| Tool capabilities vary between providers | Capability checking, graceful degradation |
| Cost increases if routing misconfigured | Budget alerts, default to cost-efficient models |
| Performance regression during migration | Phased rollout, A/B testing, easy rollback |

### Neutral

1. **Authentication Management:** Same complexity, different credentials
2. **Rate Limiting:** Each provider has limits, need to manage all
3. **Documentation:** Existing docs still valid for Claude-specific features

## Decision Permanence

**Medium permanence.**

The abstraction layer is additive - it doesn't remove existing Claude Code capability. If the abstraction proves problematic, we can continue using Claude Code directly while the abstraction matures.

The decision to use configuration-driven routing is **low permanence** - routing rules can be changed without code modifications.

The decision to support multiple providers is **high permanence** - once engineers depend on alternative providers for specific use cases, removing them would be disruptive.

## Alternatives Considered

### Alternative 1: Stay Claude-Only

**Description:** Continue with Claude Code as the only LLM provider.

**Pros:**
- No migration effort
- Simpler architecture
- Deep integration with Claude Code features

**Cons:**
- Single point of failure
- No cost optimization opportunity
- Locked to Anthropic pricing/availability

**Rejected because:** The benefits of model agnosticism (resilience, cost optimization, flexibility) outweigh the complexity costs, especially as the LLM ecosystem matures.

### Alternative 2: Full Multi-Provider Abstraction (LangChain/LlamaIndex)

**Description:** Use existing frameworks like LangChain for provider abstraction.

**Pros:**
- Battle-tested abstraction
- Large ecosystem of providers
- Community support

**Cons:**
- Heavy dependency (thousands of transitive dependencies)
- Abstracts away Claude Code's unique features
- Learning curve for team
- May not support CLI-based providers like Claude Code well

**Rejected because:** These frameworks are optimized for API-based providers and may not integrate well with Claude Code CLI's unique capabilities (native file access, MCP tools, etc.).

### Alternative 3: API-Only (No Claude Code CLI)

**Description:** Switch entirely to API-based LLM access, dropping Claude Code CLI.

**Pros:**
- Uniform provider interface
- Easier abstraction
- Standard authentication

**Cons:**
- Lose Claude Code's native tool use
- Must re-implement file operations, code execution
- Lose MCP integration benefits

**Rejected because:** Claude Code CLI provides significant value through native tool use, file operations, and MCP integration that would be expensive to replicate.

### Alternative 4: Prompt-Level Routing Only

**Description:** Use a single provider but route to different models via prompt parameters.

**Pros:**
- Simpler implementation
- Single authentication
- Consistent tool support

**Cons:**
- Limited to one provider's model family
- No cross-provider fallback
- Tied to provider's pricing structure

**Rejected because:** This provides model flexibility within a provider but doesn't address provider lock-in or cross-provider optimization opportunities.

### Alternative 5: LiteLLM as Routing Engine

**Description:** Use [LiteLLM](https://github.com/BerriAI/litellm) as the core routing and provider abstraction layer instead of custom implementation.

**Pros:**
- Battle-tested with 100+ provider support
- Built-in routing strategies (`simple-shuffle`, `least-busy`, `usage-based-routing`, `latency-based-routing`)
- Context window fallbacks handled automatically
- Distributed load balancing via Redis
- Active community and maintenance

**Cons:**
- Additional dependency
- May not integrate seamlessly with Claude Code CLI
- Less control over routing logic
- Potential overhead for simple use cases

**Status: Under Consideration.** This is a viable hybrid approach where LiteLLM handles API-based providers while Claude Code CLI remains the primary interface for complex tasks. The custom router could delegate to LiteLLM for non-Claude providers:

```python
# Hybrid approach
class HybridModelRouter:
    def __init__(self):
        self.claude_code = ClaudeCodeProvider()
        self.litellm_router = litellm.Router(
            model_list=[...],  # Non-Claude models
            routing_strategy="latency-based-routing",
        )

    async def route(self, request: LLMRequest, task_type: str):
        if self._requires_claude_code_features(request):
            return await self.claude_code.complete(request)
        else:
            return await self.litellm_router.acompletion(...)
```

## Related ADRs

| ADR | Relationship |
|-----|--------------|
| [ADR-Autonomous-Software-Engineer](../in-progress/ADR-Autonomous-Software-Engineer.md) | Parent ADR defining jib architecture; mentions "Architecture supports swapping" LLM providers |
| [ADR-Context-Sync-Strategy](../implemented/ADR-Context-Sync-Strategy-Custom-vs-MCP.md) | MCP strategy applies to model-agnostic tools; MCP provides provider-agnostic tool protocol |
| [ADR-Standardized-Logging-Interface](../in-progress/ADR-Standardized-Logging-Interface.md) | Logging must capture multi-provider LLM outputs for debugging and cost tracking |

## References

### Provider Abstraction & Routing
- [LiteLLM](https://github.com/BerriAI/litellm) - Multi-provider abstraction with 100+ providers
- [LiteLLM Router Documentation](https://docs.litellm.ai/docs/routing) - Routing strategies and fallback configuration
- [LiteLLM Proxy Load Balancing](https://docs.litellm.ai/docs/proxy/load_balancing) - Distributed load balancing patterns
- [Vercel AI SDK](https://sdk.vercel.ai/) - TypeScript-first provider abstraction

### Tool Protocols
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) - Provider-agnostic tool protocol
- [ToolRegistry Paper](https://arxiv.org/html/2507.10593v1) - Research on tool abstraction patterns

### Provider APIs
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Google Generative AI](https://ai.google.dev/docs)
- [Ollama](https://ollama.ai/) - Local model hosting

### Architecture Patterns
- [LLM Agnostic Architecture (Entrio)](https://www.entrio.io/blog/implementing-llm-agnostic-architecture-generative-ai-module) - Layered architecture approach
- [LLM Orchestration Frameworks Comparison](https://research.aimultiple.com/llm-orchestration/) - Testing and prompt normalization considerations
- [TensorWave LLM Agnostic Systems](https://tensorwave.com/blog/llm-agnostic) - Multi-LLM platform patterns
- [LangChain](https://langchain.com/) - Reference for abstraction patterns

---

**Last Updated:** 2025-11-28
**Next Review:** 2026-02-28 (Quarterly)
**Status:** Proposed
