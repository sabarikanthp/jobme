from collections.abc import Callable

from jobme.config.settings import ProviderConfig, Settings
from jobme.llm.types import Provider


class StepNotConfiguredError(Exception):
    pass


def provider_for_step(
    settings: Settings, step: str, builder: Callable[[ProviderConfig], Provider]
) -> tuple[Provider, str]:
    sm = settings.steps.get(step)
    cfg = next((p for p in settings.providers if sm and p.id == sm.provider_id), None)
    if sm is None or cfg is None:
        raise StepNotConfiguredError("Connect an AI first.")
    return builder(cfg), sm.model
