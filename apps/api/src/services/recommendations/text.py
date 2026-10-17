from src.models.domain import Pattern


def template_text(pattern: Pattern, bundle: dict) -> dict:
    raise NotImplementedError


def validate_llm_text(text: dict, bundle: dict) -> bool:
    raise NotImplementedError
