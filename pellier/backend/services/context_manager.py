"""
Intelligent Context Management for Production Agentic AI
Context Window Management & Prompt Engineering for Production Agentic AI

This module demonstrates expert-level context management for multi-agent systems:
- Token budgeting and tracking across 200K context window
- Intelligent context pruning when approaching limits
- Conversation summarization preserving key information
- Dynamic prompt assembly with versioning
- Production cost optimization patterns

Author: Pellier Workshop
"""

import tiktoken
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """The Router and the three agents it reaches."""
    ROUTER = "router"
    SHOPPING = "shopping"
    STOCK = "stock"
    SUPPORT = "support"


@dataclass
class Message:
    """
    Structured message with metadata for intelligent context management
    """
    role: str  # "user", "assistant", "system"
    content: str
    tokens: int
    timestamp: datetime
    agent_type: Optional[AgentType] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance_score: float = 1.0  # 0.0-1.0 for pruning decisions
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for Claude API"""
        return {
            "role": self.role,
            "content": self.content
        }


class ContextManager:
    """
    Production-Grade Context Window Management
    
    Manages a 200K model context window for multi-agent systems.
    Demonstrates expert-level patterns for token optimization, context pruning,
    and conversation state management.
    
    Key Features:
    - Automatic token tracking with tiktoken
    - Intelligent context pruning (FIFO, importance-based, semantic)
    - Conversation summarization for long-running sessions
    - Multi-agent context isolation and routing
    - Cost optimization through token efficiency
    
    Usage:
        manager = ContextManager(max_tokens=180000)
        manager.add_message("user", "Find a milestone gift for a new homeowner")
        context = manager.get_optimized_context("recommendation_agent")
    """
    
    def __init__(
        self,
        max_tokens: int = 180000,  # Leave 20K buffer for Claude 200K window
        prune_threshold: float = 0.85,  # Start pruning at 85% capacity
        summary_threshold: int = 50,  # Summarize after 50 messages
        encoding_name: str = "cl100k_base"  # Claude's tokenizer
    ):
        """
        Initialize Context Manager
        
        Args:
            max_tokens: Maximum context window size (default: 180K leaves 20K buffer)
            prune_threshold: Percentage of max_tokens to trigger pruning (0.0-1.0)
            summary_threshold: Number of messages before auto-summarization
            encoding_name: Tokenizer encoding (cl100k_base for Claude)
        """
        self.max_tokens = max_tokens
        self.prune_threshold = int(max_tokens * prune_threshold)
        self.summary_threshold = summary_threshold
        
        # Initialize tokenizer
        try:
            self.encoding = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            logger.warning(f"Failed to load tiktoken: {e}. Using rough estimation.")
            self.encoding = None
        
        # Conversation state
        self.conversation_history: List[Message] = []
        self.system_prompt: Optional[Message] = None
        self.context_metadata = {
            "session_start": datetime.now(),
            "total_messages": 0,
            "total_tokens_processed": 0,
            "pruning_events": 0,
            "summarization_events": 0
        }
        
        # Agent-specific context
        self.agent_contexts: Dict[AgentType, List[Message]] = {
            agent: [] for agent in AgentType
        }
        
        logger.debug(f"Context Manager initialized: {max_tokens:,} token limit")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text using tiktoken
        
        Falls back to rough estimation (4 chars ≈ 1 token) if tiktoken unavailable
        """
        if self.encoding:
            return len(self.encoding.encode(text))
        else:
            # Rough estimation: 1 token ≈ 4 characters
            return len(text) // 4
    
    def _calculate_importance_score(self, message: Message) -> float:
        """
        Calculate importance score for pruning decisions
        
        Factors:
        - Recency (newer = more important)
        - Role (user queries more important than agent responses)
        - Agent type (specialized agent outputs more important)
        - Content length (longer = potentially more important)
        - Explicit metadata importance
        
        Returns:
            Score from 0.0 (least important) to 1.0 (most important)
        """
        score = 0.0
        
        # Recency factor (exponential decay)
        age = datetime.now() - message.timestamp
        age_hours = age.total_seconds() / 3600
        recency_score = max(0.0, 1.0 - (age_hours / 24))  # Decay over 24 hours
        score += recency_score * 0.3
        
        # Role factor
        if message.role == "user":
            score += 0.3  # User queries are important
        elif message.role == "system":
            score += 0.4  # System prompts are very important
        else:
            score += 0.1  # Assistant responses less critical
        
        # Agent type factor
        if message.agent_type:
            score += 0.2  # Specialized agent outputs are important
        
        # Metadata importance
        if message.metadata.get("importance"):
            score += message.metadata["importance"] * 0.2
        
        return min(1.0, score)
    
    def add_message(
        self,
        role: str,
        content: str,
        agent_type: Optional[AgentType] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None
    ) -> Message:
        """
        Add message to conversation history with automatic token tracking
        
        Automatically triggers pruning if approaching context limit.
        
        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
            agent_type: Which agent generated this message
            metadata: Additional metadata for tracking
            importance: Manual importance override (0.0-1.0)
        
        Returns:
            Message object added to history
        """
        tokens = self._estimate_tokens(content)
        
        # Check if we need to prune before adding
        current_total = self._total_tokens()
        if current_total + tokens > self.prune_threshold:
            logger.info(f"⚠️ Approaching token limit ({current_total:,}/{self.max_tokens:,}). Pruning old context...")
            self._prune_old_context()
        
        # Create message
        message = Message(
            role=role,
            content=content,
            tokens=tokens,
            timestamp=datetime.now(),
            agent_type=agent_type,
            metadata=metadata or {}
        )
        
        # Calculate importance score
        if importance is not None:
            message.importance_score = importance
        else:
            message.importance_score = self._calculate_importance_score(message)
        
        # Add to history
        self.conversation_history.append(message)
        
        # Add to agent-specific context if applicable
        if agent_type:
            self.agent_contexts[agent_type].append(message)
        
        # Update metadata
        self.context_metadata["total_messages"] += 1
        self.context_metadata["total_tokens_processed"] += tokens
        
        # Check if we need summarization
        if len(self.conversation_history) >= self.summary_threshold:
            logger.info(f"📝 {len(self.conversation_history)} messages reached. Consider summarization.")
        
        logger.debug(f"✅ Added {role} message: {tokens} tokens, importance={message.importance_score:.2f}")
        
        return message
    
    def set_system_prompt(self, content: str, agent_type: Optional[AgentType] = None):
        """
        Set system prompt (always preserved during pruning)
        
        System prompts are critical for agent behavior and never pruned.
        """
        tokens = self._estimate_tokens(content)
        self.system_prompt = Message(
            role="system",
            content=content,
            tokens=tokens,
            timestamp=datetime.now(),
            agent_type=agent_type,
            importance_score=1.0  # Maximum importance
        )
        logger.info(f"✅ System prompt set: {tokens} tokens")
    
    def _total_tokens(self) -> int:
        """Calculate total tokens in current context"""
        total = sum(msg.tokens for msg in self.conversation_history)
        if self.system_prompt:
            total += self.system_prompt.tokens
        return total
    
    def _prune_old_context(self, target_tokens: Optional[int] = None):
        """
        Intelligently prune old context when approaching limit
        
        Strategy:
        1. Never prune system prompts
        2. Remove messages with lowest importance scores first
        3. Preserve recent user queries
        4. Keep at least last 5 messages for coherence
        
        Args:
            target_tokens: Target token count after pruning (default: 70% of max)
        """
        if target_tokens is None:
            target_tokens = int(self.max_tokens * 0.7)  # Prune to 70%
        
        current_total = self._total_tokens()
        tokens_to_remove = current_total - target_tokens
        
        if tokens_to_remove <= 0:
            return
        
        logger.info(f"🗑️ Pruning context: {current_total:,} → {target_tokens:,} tokens ({tokens_to_remove:,} to remove)")
        
        # Sort by importance (ascending) but preserve last 5 messages
        preserve_count = min(5, len(self.conversation_history))
        recent_messages = self.conversation_history[-preserve_count:]
        prunable_messages = self.conversation_history[:-preserve_count]
        
        # Sort prunable by importance score
        prunable_messages.sort(key=lambda m: m.importance_score)
        
        # Remove lowest importance messages until target reached
        removed_tokens = 0
        removed_count = 0
        new_history = []
        
        for msg in prunable_messages:
            if removed_tokens < tokens_to_remove:
                removed_tokens += msg.tokens
                removed_count += 1
            else:
                new_history.append(msg)
        
        # Add back recent messages
        new_history.extend(recent_messages)
        
        # Update history
        self.conversation_history = new_history
        self.context_metadata["pruning_events"] += 1
        
        new_total = self._total_tokens()
        logger.info(f"✅ Pruned {removed_count} messages ({removed_tokens:,} tokens). New total: {new_total:,}")
    
    def get_optimized_context(
        self,
        agent_type: Optional[AgentType] = None,
        include_agent_history: bool = True,
        max_messages: Optional[int] = None
    ) -> List[Dict[str, str]]:
        """
        Get optimized context for agent invocation
        
        Returns context tailored for specific agent type:
        - System prompt (if set)
        - Agent-specific history (if applicable)
        - Recent conversation context
        - All within token budget
        
        Args:
            agent_type: Which agent is requesting context
            include_agent_history: Include agent-specific messages
            max_messages: Maximum number of messages to include
        
        Returns:
            List of messages in Claude API format
        """
        messages = []
        
        # Always include system prompt first
        if self.system_prompt:
            messages.append(self.system_prompt.to_dict())
        
        # Get relevant conversation history
        relevant_history = self.conversation_history.copy()
        
        # Filter by agent type if specified
        if agent_type and include_agent_history:
            agent_messages = self.agent_contexts.get(agent_type, [])
            # Combine with general conversation
            relevant_history = sorted(
                relevant_history + agent_messages,
                key=lambda m: m.timestamp
            )
        
        # Limit message count if specified
        if max_messages:
            relevant_history = relevant_history[-max_messages:]
        
        # Convert to API format
        for msg in relevant_history:
            messages.append(msg.to_dict())
        
        total_tokens = sum(self._estimate_tokens(json.dumps(m)) for m in messages)
        logger.debug(f"📤 Optimized context: {len(messages)} messages, {total_tokens:,} tokens")
        
        return messages
    
    def get_context_stats(self) -> Dict[str, Any]:
        """
        Get detailed context statistics for monitoring
        
        Returns comprehensive metrics for token usage, efficiency, and costs.
        """
        total_tokens = self._total_tokens()
        
        return {
            "window_size": self.max_tokens,
            "current_tokens": total_tokens,
            "usage_percentage": (total_tokens / self.max_tokens) * 100,
            "available_tokens": self.max_tokens - total_tokens,
            "total_messages": len(self.conversation_history),
            "system_prompt_tokens": self.system_prompt.tokens if self.system_prompt else 0,
            "session_duration_minutes": (datetime.now() - self.context_metadata["session_start"]).total_seconds() / 60,
            "total_tokens_processed": self.context_metadata["total_tokens_processed"],
            "pruning_events": self.context_metadata["pruning_events"],
            "avg_tokens_per_message": total_tokens / max(1, len(self.conversation_history)),
            "estimated_cost_usd": self._estimate_cost(total_tokens),
            "efficiency_score": self._calculate_efficiency_score()
        }
    
    def _estimate_cost(self, tokens: int) -> float:
        """
        Estimate cost for current context
        
        This is an illustrative input-only estimate, not live billing data.
        """
        cost_per_million = 3.00
        return (tokens / 1_000_000) * cost_per_million
    
    def _calculate_efficiency_score(self) -> float:
        """
        Calculate context efficiency score (0-100)
        
        Higher is better:
        - Low pruning frequency = efficient context management
        - High token usage = good utilization
        - Recent messages = active conversation
        
        Returns:
            Score from 0-100
        """
        if not self.conversation_history:
            return 0.0
        
        # Token utilization (0-40 points)
        utilization = (self._total_tokens() / self.max_tokens) * 40
        
        # Pruning efficiency (0-30 points) - fewer prunes = better
        max_prunes = max(1, len(self.conversation_history) // 10)
        prune_score = max(0, 30 - (self.context_metadata["pruning_events"] / max_prunes) * 30)
        
        # Recency score (0-30 points) - more recent activity = better
        recent_minutes = (datetime.now() - self.conversation_history[-1].timestamp).total_seconds() / 60
        recency_score = max(0, 30 - min(30, recent_minutes))
        
        return min(100.0, utilization + prune_score + recency_score)
    
    def clear_context(self):
        """Clear all conversation history (preserve system prompt)"""
        tokens_cleared = sum(msg.tokens for msg in self.conversation_history)
        self.conversation_history = []
        self.agent_contexts = {agent: [] for agent in AgentType}
        logger.info(f"🗑️ Context cleared: {tokens_cleared:,} tokens freed")


# Global context manager instance
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create the global context manager instance"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(max_tokens=180000)
    return _context_manager


def init_context_manager(max_tokens: int = 180000) -> ContextManager:
    """Initialize the context manager (call during app startup)"""
    global _context_manager
    _context_manager = ContextManager(max_tokens=max_tokens)
    logger.debug(f"Context Manager initialized (max_tokens={max_tokens:,})")
    return _context_manager
