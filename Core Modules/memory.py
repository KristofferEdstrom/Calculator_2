"""
memory.py

Manages the calculator's manual memory register.

Supported operations:
- M+ : add a value
- M- : subtract a value
- MR : recall the stored value
- MC : clear the stored value
"""


class MemoryRegister:
    """Stores and manages one calculator memory value."""

    def __init__(self) -> None:
        """Initialize memory at zero."""
        self._value: float = 0.0

    def add(self, value: float) -> float:
        """
        Add a value to memory.

        Returns the updated memory value.
        """
        self._value += value
        return self._value

    def subtract(self, value: float) -> float:
        """
        Subtract a value from memory.

        Returns the updated memory value.
        """
        self._value -= value
        return self._value

    def recall(self) -> float:
        """Return the current memory value."""
        return self._value

    def clear(self) -> None:
        """Reset memory to zero."""
        self._value = 0.0

    def has_value(self) -> bool:
        """Return True when memory contains a non-zero value."""
        return self._value != 0