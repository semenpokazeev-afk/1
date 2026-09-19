"""
ARBITER Multi-Provider Cost Calculator (Module 4)
Precise pre-flight estimates and post-call actual cost calculation with prompt caching discounts.
"""

from typing import Dict, Any, Tuple


# Pricing per 1M tokens ($)
# (input_price_per_1m, output_price_per_1m, cached_input_price_per_1m)
MODEL_PRICING: Dict[str, Tuple[float, float, float]] = {
    # OpenAI
    "gpt-4o": (2.50, 10.00, 1.25),
    "gpt-4o-mini": (0.15, 0.60, 0.075),
    "gpt-4-turbo": (10.00, 30.00, 5.00),
    
    # Anthropic
    "claude-3-5-sonnet": (3.00, 15.00, 0.30),
    "claude-3-5-haiku": (0.80, 4.00, 0.08),
    "claude-3-opus": (15.00, 75.00, 1.50),

    # Google Gemini
    "gemini-1.5-pro": (1.25, 5.00, 0.3125),
    "gemini-1.5-flash": (0.075, 0.30, 0.01875),
    "gemini-2.0-flash": (0.10, 0.40, 0.025),

    # Mock / Local
    "mock-gpt-4o": (2.50, 10.00, 1.25),
    "mock-claude-3-5-sonnet": (3.00, 15.00, 0.30),
    "mock-gemini-1.5-flash": (0.075, 0.30, 0.01875),
    "mock-llama-3": (0.05, 0.05, 0.01)
}


class CostCalculator:
    """
    Computes pricing and savings across providers.
    """

    @staticmethod
    def estimate_cost(input_tokens: int, estimated_output_tokens: int, model: str) -> float:
        """
        Pre-flight cost estimation based on input tokens and expected max completion.
        """
        pricing = MODEL_PRICING.get(model, (1.0, 3.0, 0.5))  # Default conservative pricing
        inp_rate, out_rate, _ = pricing

        cost = (input_tokens / 1_000_000.0) * inp_rate + (estimated_output_tokens / 1_000_000.0) * out_rate
        return round(cost, 6)

    @staticmethod
    def calculate_actual_cost(
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int,
        model: str
    ) -> float:
        """
        Actual cost calculation including cached prompt discounts.
        """
        pricing = MODEL_PRICING.get(model, (1.0, 3.0, 0.5))
        inp_rate, out_rate, cached_rate = pricing

        uncached_prompt_tokens = max(0, prompt_tokens - cached_tokens)

        cost = (
            (uncached_prompt_tokens / 1_000_000.0) * inp_rate +
            (cached_tokens / 1_000_000.0) * cached_rate +
            (completion_tokens / 1_000_000.0) * out_rate
        )
        return round(cost, 6)
