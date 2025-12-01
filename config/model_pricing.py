#!/usr/bin/env python3
"""
Model Pricing Configuration for james-in-a-box (jib)

Provides current pricing information for LLM models used by jib.
Pricing is in USD per million tokens (MTok).

This configuration is used by:
- Inefficiency detector for cost estimates
- Usage analytics and reporting

Pricing last updated: 2025-12-01
Source: https://www.anthropic.com/pricing

Usage:
    from config.model_pricing import get_model_pricing, get_active_model

    pricing = get_model_pricing()
    model = get_active_model()
    input_cost = pricing[model]["input"]
    output_cost = pricing[model]["output"]
"""

from typing import TypedDict


class ModelPricing(TypedDict):
    """Pricing per million tokens (MTok) in USD."""

    input: float  # Cost per MTok for input tokens
    output: float  # Cost per MTok for output tokens


# Current Anthropic Claude model pricing (USD per million tokens)
# Updated: 2025-12-01
# Source: https://www.anthropic.com/pricing
MODEL_PRICING: dict[str, ModelPricing] = {
    # Claude Opus 4.5 - Most capable model
    "claude-opus-4-5-20251101": {
        "input": 15.0,
        "output": 75.0,
    },
    # Claude Sonnet 4.5 - Balanced performance/cost
    "claude-sonnet-4-5-20250929": {
        "input": 3.0,
        "output": 15.0,
    },
    # Claude Sonnet 4 - Previous generation balanced
    "claude-sonnet-4-20250514": {
        "input": 3.0,
        "output": 15.0,
    },
    # Claude Haiku 3.5 - Fast and cost-effective
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.0,
    },
    # Aliases for common names
    "opus": {
        "input": 15.0,
        "output": 75.0,
    },
    "sonnet": {
        "input": 3.0,
        "output": 15.0,
    },
    "haiku": {
        "input": 0.80,
        "output": 4.0,
    },
}

# The active model used by jib (can be overridden via environment or config)
# This should match the model specified in claude code configuration
DEFAULT_ACTIVE_MODEL = "claude-opus-4-5-20251101"


def get_model_pricing(model: str | None = None) -> ModelPricing:
    """
    Get pricing for a specific model or all models.

    Args:
        model: Model name/ID. If None, returns pricing for active model.

    Returns:
        ModelPricing dict with input/output costs per MTok.

    Raises:
        KeyError: If model not found in pricing table.
    """
    if model is None:
        model = get_active_model()

    # Try exact match first
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]

    # Try to match by prefix (e.g., "claude-sonnet-4" matches "claude-sonnet-4-20250514")
    for known_model in MODEL_PRICING:
        if model.startswith(known_model) or known_model.startswith(model):
            return MODEL_PRICING[known_model]

    # Default to sonnet pricing if unknown (most commonly used)
    return MODEL_PRICING["sonnet"]


def get_active_model() -> str:
    """
    Get the currently active model used by jib.

    Checks (in order):
    1. CLAUDE_MODEL environment variable
    2. Default active model constant

    Returns:
        Model ID string.
    """
    import os

    return os.environ.get("CLAUDE_MODEL", DEFAULT_ACTIVE_MODEL)


def get_all_pricing() -> dict[str, ModelPricing]:
    """Get pricing for all known models."""
    return dict(MODEL_PRICING)


def calculate_cost(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    """
    Calculate the cost for a given number of tokens.

    Args:
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.
        model: Model to use for pricing. If None, uses active model.

    Returns:
        Total cost in USD.
    """
    pricing = get_model_pricing(model)
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


def calculate_blended_cost(
    tokens: int, input_ratio: float = 0.4, model: str | None = None
) -> float:
    """
    Calculate cost using a blended rate (for when input/output split is unknown).

    Args:
        tokens: Total number of tokens.
        input_ratio: Estimated ratio of input tokens (default 40%).
        model: Model to use for pricing. If None, uses active model.

    Returns:
        Estimated total cost in USD.
    """
    pricing = get_model_pricing(model)
    output_ratio = 1.0 - input_ratio
    blended_rate = (input_ratio * pricing["input"]) + (output_ratio * pricing["output"])
    return (tokens / 1_000_000) * blended_rate


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Model pricing utility")
    parser.add_argument("--model", help="Model to get pricing for")
    parser.add_argument("--list", action="store_true", help="List all models and pricing")
    parser.add_argument("--active", action="store_true", help="Show active model")
    parser.add_argument(
        "--calculate",
        nargs=2,
        type=int,
        metavar=("INPUT", "OUTPUT"),
        help="Calculate cost for INPUT and OUTPUT tokens",
    )

    args = parser.parse_args()

    if args.list:
        print("Model Pricing (USD per million tokens):")
        print("=" * 50)
        for model, pricing in get_all_pricing().items():
            print(f"{model}:")
            print(f"  Input:  ${pricing['input']:.2f}/MTok")
            print(f"  Output: ${pricing['output']:.2f}/MTok")
    elif args.active:
        model = get_active_model()
        pricing = get_model_pricing(model)
        print(f"Active model: {model}")
        print(f"  Input:  ${pricing['input']:.2f}/MTok")
        print(f"  Output: ${pricing['output']:.2f}/MTok")
    elif args.calculate:
        input_tokens, output_tokens = args.calculate
        model = args.model or get_active_model()
        cost = calculate_cost(input_tokens, output_tokens, model)
        print(f"Model: {model}")
        print(f"Input tokens: {input_tokens:,}")
        print(f"Output tokens: {output_tokens:,}")
        print(f"Total cost: ${cost:.4f}")
    elif args.model:
        pricing = get_model_pricing(args.model)
        print(f"Model: {args.model}")
        print(f"  Input:  ${pricing['input']:.2f}/MTok")
        print(f"  Output: ${pricing['output']:.2f}/MTok")
    else:
        # Show active model by default
        model = get_active_model()
        pricing = get_model_pricing(model)
        print(f"Active model: {model}")
        print(f"  Input:  ${pricing['input']:.2f}/MTok")
        print(f"  Output: ${pricing['output']:.2f}/MTok")
        print()
        print("Use --list to see all models, --help for more options")
