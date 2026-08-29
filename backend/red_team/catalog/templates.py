"""Attack template loader and renderer for parameterized red-team campaigns."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TemplateStep:
    """A single parameterized step within an attack template."""

    phase: str
    action: str
    surface: str
    template: str
    params: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class AttackTemplate:
    """A multi-step structured attack template for an adversary objective."""

    id: str
    name: str
    description: str
    target_layers: list[str]
    surfaces: list[str]
    techniques: list[str]
    steps: list[TemplateStep]
    success_signal: str


TEMPLATES_DIR = Path(__file__).parent / "templates"


def load_template(template_id: str) -> AttackTemplate:
    """Load an attack template from its YAML definition.

    Args:
        template_id: Identifier of the template (matches filename without .yaml).

    Returns:
        AttackTemplate: The parsed template object.

    Raises:
        FileNotFoundError: If the template file does not exist.
        ValueError: If required fields are missing in the YAML.
    """
    clean_id = template_id.removesuffix(".yaml")
    file_path = TEMPLATES_DIR / f"{clean_id}.yaml"
    if not file_path.exists():
        raise FileNotFoundError(f"Attack template not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise TypeError(f"Invalid template format in {file_path}")

    raw_steps = data.get("steps", [])
    steps = [
        TemplateStep(
            phase=s.get("phase", "execution"),
            action=s.get("action", ""),
            surface=s.get("surface", "user_message"),
            template=s.get("template", ""),
            params=s.get("params", {}),
        )
        for s in raw_steps
    ]

    return AttackTemplate(
        id=data.get("id", clean_id),
        name=data.get("name", clean_id),
        description=data.get("description", ""),
        target_layers=data.get("target_layers", []),
        surfaces=data.get("surfaces", []),
        techniques=data.get("techniques", []),
        steps=steps,
        success_signal=data.get("success_signal", ""),
    )


def load_all_templates() -> dict[str, AttackTemplate]:
    """Load all YAML attack templates available in the templates directory.

    Returns:
        dict[str, AttackTemplate]: Mapping of template ID to AttackTemplate.
    """
    templates: dict[str, AttackTemplate] = {}
    if not TEMPLATES_DIR.exists():
        return templates

    for yaml_file in sorted(TEMPLATES_DIR.glob("*.yaml")):
        tmpl = load_template(yaml_file.stem)
        templates[tmpl.id] = tmpl

    return templates


def render_step(step: TemplateStep, params: dict[str, str]) -> str:
    """Render a step's template string by substituting parameter placeholders.

    Args:
        step: The TemplateStep to render.
        params: Dictionary of parameter key-value pairs to substitute.

    Returns:
        str: Rendered payload string with `{key}` placeholders substituted.
    """
    rendered = step.template
    for key, value in params.items():
        rendered = rendered.replace(f"{{{key}}}", str(value))
    return rendered
