"""Ordered, deterministic DXF exports. Importing metadata never loads CAD code.

Writers accept (cfg, doc, path); verifiers accept (doc, path) and return
(passed, measurements). Implementations are loaded only inside the worker.
"""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class OutputFormat:
    filename: str
    write: Callable
    verify: Callable
    rule_id: str
    target: str
    path_attribute: str | None = None

    def path(self, cfg):
        # Preserve Design.AI overrides for callers predating the registry.
        return getattr(cfg, self.path_attribute) if self.path_attribute else cfg.OUT / self.filename


def _write_ai(cfg, doc, path):
    from . import ai_export
    return ai_export.write(cfg, doc, path)


def _verify_ai(doc, path):
    from . import ai_export
    return ai_export.verify(doc, path)


AI = OutputFormat("window.ai", _write_ai, _verify_ai,
                  "ai_export_matches_saved_dxf", "saved_ai", path_attribute="AI")
FORMATS = (AI,)


def filenames():
    return tuple(fmt.filename for fmt in FORMATS)


def rule_ids():
    return tuple(fmt.rule_id for fmt in FORMATS)
