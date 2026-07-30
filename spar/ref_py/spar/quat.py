"""Quaternion- und Vektor-Mathematik fuer die Referenz-Implementierung.

Reines Python, absichtlich ohne numpy: die Conformance-Suite soll gegen eine
Implementierung gepruefte Werte liefern, deren Rechenweg vollstaendig sichtbar ist.

Diese Ebene ist Gleitkomma und darf es sein -- sie wird ausschliesslich zur Bake-Zeit und
zum Rendern benutzt, nie im Gameplay-Pfad (siehe ``spec/determinism.md``).

Konvention: Quaternion als ``(x, y, z, w)``, wie in glTF.
"""

from __future__ import annotations

import math

Vec3 = tuple[float, float, float]
Quat = tuple[float, float, float, float]

IDENTITY: Quat = (0.0, 0.0, 0.0, 1.0)


def mul(a: Quat, b: Quat) -> Quat:
    """Hintereinanderausfuehrung: erst ``b``, dann ``a``."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    )


def apply(q: Quat, v: Vec3) -> Vec3:
    """Rotiert den Vektor ``v`` mit dem Quaternion ``q``."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * (q_vec x v)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    )


def conjugate(q: Quat) -> Quat:
    x, y, z, w = q
    return (-x, -y, -z, w)


def normalize(q: Quat) -> Quat:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n == 0.0:
        return IDENTITY
    return (x / n, y / n, z / n, w / n)


def canonical(q: Quat) -> Quat:
    """Erzwingt ``w >= 0``.

    Ohne diese Normierung beschreiben zwei verschiedene Bitmuster dieselbe Rotation, und
    Byte-Vergleiche in der Conformance-Suite schlagen grundlos fehl. Vom glTF-Profil
    gefordert.
    """
    q = normalize(q)
    return tuple(-c for c in q) if q[3] < 0.0 else q  # type: ignore[return-value]


def from_axis_angle(axis: Vec3, angle_rad: float) -> Quat:
    ax, ay, az = axis
    n = math.sqrt(ax * ax + ay * ay + az * az)
    if n == 0.0:
        return IDENTITY
    s = math.sin(angle_rad * 0.5) / n
    return canonical((ax * s, ay * s, az * s, math.cos(angle_rad * 0.5)))


def from_euler_zyx(z_deg: float, y_deg: float, x_deg: float) -> Quat:
    """Bequemlichkeit fuers Authoring von Hand. Reihenfolge Z, dann Y, dann X."""
    qz = from_axis_angle((0.0, 0.0, 1.0), math.radians(z_deg))
    qy = from_axis_angle((0.0, 1.0, 0.0), math.radians(y_deg))
    qx = from_axis_angle((1.0, 0.0, 0.0), math.radians(x_deg))
    return canonical(mul(qz, mul(qy, qx)))


def mirror_x(q: Quat) -> Quat:
    """Spiegelt eine Rotation an der YZ-Ebene.

    Die Reflexion konjugiert die Rotation: die x-Komponente bleibt, y und z kippen.
    Naives Negieren aller Winkel oder ein ``facingSign``-Faktor im FK ist falsch und
    vertauscht bei asymmetrischen Rest-Posen die Glieder.
    """
    x, y, z, w = q
    return canonical((x, -y, -z, w))


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def length(v: Vec3) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
