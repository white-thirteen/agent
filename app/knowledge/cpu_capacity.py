"""Process-wide, non-queuing capacity for local CPU inference."""

from threading import Lock

cpu_capacity = Lock()
