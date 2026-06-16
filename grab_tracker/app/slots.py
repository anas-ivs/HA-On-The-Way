class SlotManager:
    """Fixed pool of N tracking slots. Each slot maps to one HA MQTT device
    (`Grab Order 1`..`Grab Order N`). A token (order) occupies one slot for its lifetime."""

    def __init__(self, size: int):
        self.size = max(1, int(size))
        self._slots = {n: None for n in range(1, self.size + 1)}  # slot -> token

    def claim(self, token: str):
        """Return the slot already holding this token, else the first free slot, else None."""
        existing = self.slot_for(token)
        if existing is not None:
            return existing
        for n, t in self._slots.items():
            if t is None:
                self._slots[n] = token
                return n
        return None

    def release(self, token: str):
        for n, t in self._slots.items():
            if t == token:
                self._slots[n] = None
                return n
        return None

    def slot_for(self, token: str):
        for n, t in self._slots.items():
            if t == token:
                return n
        return None

    def token(self, n: int):
        return self._slots.get(n)

    def all_slots(self):
        return list(self._slots.keys())

    def free_slots(self):
        return [n for n, t in self._slots.items() if t is None]

    def used(self):
        return [t for t in self._slots.values() if t is not None]
