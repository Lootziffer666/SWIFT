"""SPAR -- engine-agnostischer Fighter-Core, Referenz-Implementierung.

Engine-frei: kein Renderer, keine Engine-Typen, keine Bildverarbeitung. Diese
Implementierung ist das Orakel, gegen das die Conformance-Vektoren erzeugt werden.
"""

from .rig import Rig, Bone, Joint, Contact, RigError, load_builtin

__all__ = ["Rig", "Bone", "Joint", "Contact", "RigError", "load_builtin"]
__version__ = "0.1.0"
