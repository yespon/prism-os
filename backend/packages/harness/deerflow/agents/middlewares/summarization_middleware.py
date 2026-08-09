"""Middleware for automatic conversation summarization with marked summary messages.

This middleware wraps LangChain's SummarizationMiddleware to add frontend-compatible
marking for summary messages.
"""

import logging
from typing import Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from deerflow.config import get_app_config
from deerflow.config.summarization_config import get_summarization_config
from deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)

# Default summarization trigger when model's max_input_tokens is not configured
DEFAULT_SUMMARIZATION_TRIGGER_TOKENS = 12000
# Fraction of model's max_input_tokens to use as trigger threshold
SUMMARIZATION_TRIGGER_FRACTION = 0.35
# Cap on auto-calculated trigger to avoid over-delaying summarization
MAX_AUTO_TRIGGER_TOKENS = 120000
# Hard-cap fraction: if tokens exceed this % of model's max, force summarization regardless of trigger
HARD_CAP_FRACTION = 0.80


class MarkedSummaryHumanMessage(HumanMessage):
    """A HumanMessage that is marked as a conversation summary for frontend display."""

    def __init__(self, content: str, **kwargs):
        # Ensure additional_kwargs exists and mark it as summary
        additional_kwargs = kwargs.get("additional_kwargs", {})
        additional_kwargs["is_summary"] = True
        kwargs["additional_kwargs"] = additional_kwargs
        super().__init__(content=content, **kwargs)


class DeerflowSummarizationMiddleware(AgentMiddleware):
    """Custom summarization middleware that marks summary messages for frontend display.

    This middleware wraps LangChain's SummarizationMiddleware to ensure that summary
    messages are marked with additional_kwargs.is_summary = True, allowing the
    frontend to render them with special styling (collapsed card instead of user bubble).
    """

    state_schema = AgentState

    def __init__(self, conversation_model_name: str) -> None:
        config = get_summarization_config()

        if not config.enabled:
            logger.warning(
                "DeerflowSummarizationMiddleware initialized but summarization is disabled in config"
            )
            self._middleware = None
            return

        # Use the config-specified model if set, otherwise fall back to the conversation's model
        summarization_model_name = config.model_name or conversation_model_name

        # Resolve via factory so provider-specific settings (api_key, base_url, etc.) are applied
        try:
            summarization_model = create_chat_model(name=summarization_model_name)
        except ValueError:
            logger.warning(
                "Model '%s' not found for summarization; skipping summarization.",
                summarization_model_name,
            )
            self._middleware = None
            return

        # Save conversation model name for hard-cap computation in __call__
        self._conversation_model_name = conversation_model_name

        # Build trigger — auto-calculate from model's max_input_tokens if available
        trigger = config.trigger
        if trigger is None:
            trigger = ("tokens", DEFAULT_SUMMARIZATION_TRIGGER_TOKENS)
        elif isinstance(trigger, list):
            trigger = [t.to_tuple() for t in trigger]
        else:
            trigger = trigger.to_tuple()

        # Override with auto-calculated threshold from model's context window
        try:
            model_cfg = get_app_config().get_model_config(conversation_model_name)
            if model_cfg and model_cfg.max_input_tokens:
                auto_tokens = min(
                    int(model_cfg.max_input_tokens * SUMMARIZATION_TRIGGER_FRACTION),
                    MAX_AUTO_TRIGGER_TOKENS,
                )
                trigger = ("tokens", auto_tokens)
                logger.info(
                    "Auto-calculated summarization trigger for model '%s': %d tokens (max_input=%d * %.0f%%)",
                    conversation_model_name, auto_tokens, model_cfg.max_input_tokens, SUMMARIZATION_TRIGGER_FRACTION * 100,
                )
            else:
                # No model config or no max_input_tokens — fall back to absolute token count
                # to avoid fraction-trigger requiring model profile in SummarizationMiddleware
                trigger = ("tokens", DEFAULT_SUMMARIZATION_TRIGGER_TOKENS)
                logger.warning(
                    "Model '%s' has no max_input_tokens configured. Using default trigger: %d tokens.",
                    conversation_model_name, DEFAULT_SUMMARIZATION_TRIGGER_TOKENS,
                )
        except Exception:
            # If model config lookup fails entirely, use safe defaults
            trigger = ("tokens", DEFAULT_SUMMARIZATION_TRIGGER_TOKENS)
            logger.warning(
                "Failed to look up model config for '%s'. Using default trigger: %d tokens.",
                conversation_model_name, DEFAULT_SUMMARIZATION_TRIGGER_TOKENS,
            )

        # Convert keep to tuple format
        keep_tuple = config.keep.to_tuple()

        # Initialize the base SummarizationMiddleware with custom message class
        self._middleware = SummarizationMiddleware(
            model=summarization_model,
            trigger=trigger,
            keep=keep_tuple,
            trim_tokens_to_summarize=config.trim_tokens_to_summarize,
            prompt_template=config.summary_prompt,
            message_class=MarkedSummaryHumanMessage,
        )

    @override
    def __call__(
        self,
        state: AgentState,
        runtime: Runtime[AgentState],
    ):
        """Delegate to the underlying SummarizationMiddleware."""
        if self._middleware is None:
            return None
        return self._middleware(state, runtime)

    @override
    def before_model(self, state: AgentState, runtime: Runtime[AgentState]) -> dict[str, Any] | None:
        """Check for hard-cap condition and force summarization if needed."""
        if self._middleware is None:
            return None

        # First, let the base middleware do its normal check
        result = self._middleware.before_model(state, runtime)
        if result is not None:
            # Base middleware already triggered summarization
            return result

        # Hard-cap protection: if base middleware didn't trigger (e.g. because
        # approximate token counting underestimated), check if we're dangerously
        # close to the model's context limit.
        messages = state.get("messages", [])
        if not messages:
            return None

        try:
            model_cfg = get_app_config().get_model_config(self._conversation_model_name)
            if not (model_cfg and model_cfg.max_input_tokens):
                return None

            hard_cap = int(model_cfg.max_input_tokens * HARD_CAP_FRACTION)
            approx_tokens = self._middleware.token_counter(messages)

            if approx_tokens < hard_cap:
                return None

            logger.warning(
                "Hard-cap triggered: approx %d tokens >= %d (%.0f%% of model max %d). Forcing summarization.",
                approx_tokens, hard_cap, HARD_CAP_FRACTION * 100, model_cfg.max_input_tokens,
            )

            # Force summarization: temporarily set a low token trigger to make
            # _should_summarize return True, then invoke the summarization logic.
            original_trigger = self._middleware._trigger_conditions
            try:
                # Override trigger to force summarization
                self._middleware._trigger_conditions = [("tokens", 1)]
                forced_result = self._middleware.before_model(state, runtime)
                return forced_result
            finally:
                self._middleware._trigger_conditions = original_trigger
        except Exception:
            pass

        return None

    @override
    async def abefore_model(self, state: AgentState, runtime: Runtime[AgentState]) -> dict[str, Any] | None:
        """Async version: check for hard-cap condition and force summarization if needed."""
        if self._middleware is None:
            return None

        # First, let the base middleware do its normal check
        result = await self._middleware.abefore_model(state, runtime)
        if result is not None:
            return result

        messages = state.get("messages", [])
        if not messages:
            return None

        try:
            model_cfg = get_app_config().get_model_config(self._conversation_model_name)
            if not (model_cfg and model_cfg.max_input_tokens):
                return None

            hard_cap = int(model_cfg.max_input_tokens * HARD_CAP_FRACTION)
            approx_tokens = self._middleware.token_counter(messages)

            if approx_tokens < hard_cap:
                return None

            logger.warning(
                "Hard-cap triggered (async): approx %d tokens >= %d (%.0f%% of model max %d). Forcing summarization.",
                approx_tokens, hard_cap, HARD_CAP_FRACTION * 100, model_cfg.max_input_tokens,
            )

            original_trigger = self._middleware._trigger_conditions
            try:
                self._middleware._trigger_conditions = [("tokens", 1)]
                forced_result = await self._middleware.abefore_model(state, runtime)
                return forced_result
            finally:
                self._middleware._trigger_conditions = original_trigger
        except Exception:
            pass

        return None
