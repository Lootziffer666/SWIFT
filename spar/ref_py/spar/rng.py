"""xorshift128 -- der in der Spec festgelegte PRNG.

Die Zufallsfunktion der Wirtssprache ist untauglich: ``random``, ``Math.random`` und
``rand()`` erzeugen in verschiedenen Sprachen und Versionen verschiedene Folgen. Ein
Replay waere damit nicht reproduzierbar und zwei konforme Implementierungen wuerden
auseinanderlaufen.

Der Seed gehoert zum Input-Log.
"""

from __future__ import annotations

MASK32 = 0xFFFFFFFF


class Xorshift128:
    __slots__ = ("x", "y", "z", "w")

    def __init__(self, seed: int = 0x2545F491) -> None:
        seed &= MASK32
        self.x = seed or 0x2545F491
        self.y = (seed * 1812433253 + 1) & MASK32
        self.z = (self.y * 1812433253 + 1) & MASK32
        self.w = (self.z * 1812433253 + 1) & MASK32

    def next_u32(self) -> int:
        t = self.x ^ ((self.x << 11) & MASK32)
        self.x, self.y, self.z = self.y, self.z, self.w
        self.w = (self.w ^ (self.w >> 19)) ^ (t ^ (t >> 8))
        return self.w & MASK32

    def below(self, n: int) -> int:
        """Gleichverteilt in ``[0, n)``.

        Rejection Sampling statt Modulo: ``% n`` verzerrt die Verteilung, wenn ``n``
        kein Teiler von 2^32 ist, und die Verzerrung faellt in verschiedenen
        Implementierungen unterschiedlich aus, sobald jemand sie "wegoptimiert".
        """
        if n <= 0:
            raise ValueError("n muss positiv sein")
        limit = (1 << 32) - ((1 << 32) % n)
        while True:
            v = self.next_u32()
            if v < limit:
                return v % n

    def state(self) -> list[int]:
        return [self.x, self.y, self.z, self.w]
