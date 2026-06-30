from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter

from customer_service.bootstrap.config import Settings


@dataclass(frozen=True)
class ModuleDefinition:
    name: str
    version: str
    enabled: Callable[[Settings], bool]
    router: APIRouter
    dependencies: tuple[str, ...] = ()


class ModuleRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._modules: dict[str, ModuleDefinition] = {}

    def register(self, module: ModuleDefinition) -> None:
        if module.name in self._modules:
            raise ValueError(f"Duplicate module: {module.name}")
        self._modules[module.name] = module

    def enabled_modules(self) -> list[ModuleDefinition]:
        enabled = [m for m in self._modules.values() if m.enabled(self._settings)]
        enabled_names = {m.name for m in enabled}
        for module in enabled:
            missing = set(module.dependencies) - enabled_names
            if missing:
                raise RuntimeError(
                    f"Module '{module.name}' requires enabled modules: {sorted(missing)}"
                )
        return enabled

