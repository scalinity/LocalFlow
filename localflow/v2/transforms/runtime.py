"""Connect prompt jobs to the existing store and eligible local memory.

No provider or index work runs while constructing these services. Context is
off unless the caller deliberately selects a project or enables personal use.
"""

def create_services(store, transforms, transformer, *, background_allowed=lambda: True):
    from ..memory import MemoryStore
    from .intelligence import IntelligenceService
    memory = MemoryStore(store)

    from .intelligence import memory_callbacks
    intelligence = IntelligenceService(store, transforms, transformer,
        **memory_callbacks(memory), background_allowed=background_allowed)
    from .learning import ActivityLearning
    intelligence.activity = ActivityLearning(memory, intelligence, transformer)
    return memory, intelligence
