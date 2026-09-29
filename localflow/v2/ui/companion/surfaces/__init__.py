"""The companion's surfaces: each module registers its allowlisted
commands on the controller's bridge and may provide a read model."""

from __future__ import annotations

from .common import Background, OpIds

READ_MODELS = {}


def register_all(ctl):
    from . import history, dictionary, settings, library, insights, scratchpad
    ctl.ops = OpIds()
    ctl.background = Background()
    for mod in (history, dictionary, settings, library, insights,
                scratchpad):
        mod.register(ctl)
        READ_MODELS.update(getattr(mod, "READ_MODELS", {}))
