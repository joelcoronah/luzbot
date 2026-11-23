"""luzbot: get a Telegram message when the power goes out at home.

A device at home sends a heartbeat to a server every minute. When the
heartbeats stop, the server assumes the house lost power (or internet)
and notifies you; when they come back, it tells you how long it lasted.
"""

__version__ = "0.1.0"
