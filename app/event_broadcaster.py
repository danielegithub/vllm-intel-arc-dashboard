"""
Thread-safe event broadcaster for real-time logging and system events.
Supports multiple subscribers with async generators.
"""

import asyncio
from typing import AsyncGenerator, Set
from app.logging_config import logger


class EventBroadcaster:
    """
    Thread-safe event broadcaster for WebSocket connections and log streaming.
    
    Multiple subscribers (WebSocket clients, etc.) can subscribe to events.
    When an event is broadcasted, it's delivered to all active subscribers.
    
    Example:
        broadcaster = EventBroadcaster()
        
        # In a background task:
        await broadcaster.broadcast("System event message\n")
        
        # In WebSocket handler:
        async for message in broadcaster.subscribe():
            await websocket.send_text(message)
    """
    
    def __init__(self, max_queue_size: int = 1000):
        """
        Initialize the broadcaster.
        
        Args:
            max_queue_size: Maximum messages per subscriber queue
        """
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._message_count = 0
    
    async def subscribe(self) -> AsyncGenerator[str, None]:
        """
        Create a new subscriber.
        
        Yields:
            Messages broadcasted to this subscriber
            
        Usage:
            async for msg in broadcaster.subscribe():
                await websocket.send_text(msg)
        """
        # Create a queue for this subscriber
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        
        # Register subscriber
        async with self._lock:
            self._subscribers.add(queue)
            logger.debug(f"New subscriber registered. Total: {len(self._subscribers)}")
        
        try:
            while True:
                # Wait for message
                msg = await queue.get()
                yield msg
        except GeneratorExit:
            logger.debug("Subscriber generator closed")
        finally:
            # Cleanup on disconnect
            async with self._lock:
                self._subscribers.discard(queue)
                logger.debug(f"Subscriber removed. Total: {len(self._subscribers)}")
    
    async def broadcast(self, message: str) -> int:
        """
        Broadcast a message to all active subscribers.
        
        Args:
            message: The message to broadcast
            
        Returns:
            Number of subscribers that received the message
            
        Note:
            If a subscriber's queue is full, the message is skipped for that
            subscriber to prevent blocking. This is normal for live log streaming.
        """
        if not message:
            return 0
        
        async with self._lock:
            # Snapshot subscribers to avoid holding lock during put operations
            subscribers_copy = list(self._subscribers)
            delivered = 0
            
            for queue in subscribers_copy:
                try:
                    # Try non-blocking put
                    queue.put_nowait(message)
                    delivered += 1
                except asyncio.QueueFull:
                    # Subscriber's queue is full (slow consumer)
                    # Skip rather than block, to keep broadcasting fast
                    logger.debug(f"Subscriber queue full, skipping message")
                except Exception as e:
                    logger.error(f"Error broadcasting to subscriber: {e}")
            
            self._message_count += 1
            
            return delivered
    
    async def get_stats(self) -> dict:
        """
        Get broadcaster statistics.
        
        Returns:
            Dictionary with subscriber count and total messages
        """
        async with self._lock:
            return {
                "active_subscribers": len(self._subscribers),
                "total_messages": self._message_count
            }
    
    async def clear(self):
        """
        Clear all subscribers and reset message count.
        Useful for testing or shutdown.
        """
        async with self._lock:
            self._subscribers.clear()
            self._message_count = 0
            logger.info("EventBroadcaster cleared")
