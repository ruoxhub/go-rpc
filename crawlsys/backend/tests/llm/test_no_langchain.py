"""Guard the production runtime against reintroducing OpenAI Agents SDK."""

import ast
import re
import tomllib
from pathlib import Path

import pytest


ALLOWED_BUSINESS_PACKAGE = "agents.tiktok_video_analysis"
LEGACY_SYMBOLS = {"configure_agents_sdk", "analysis_agents"}


def _is_forbidden_agents_import(module: str) -> bool:
    return module == "agents" or (
        module.startswith("agents.")
        and not module.startswith(f"{ALLOWED_BUSINESS_PACKAGE}.")
        and module != ALLOWED_BUSINESS_PACKAGE
    )


def _module_violation(module: str) -> str | None:
    if _is_forbidden_agents_import(module):
        return f"forbidden import {module}"
    if module == "analysis_agents" or module.startswith("analysis_agents."):
        return "legacy symbol analysis_agents"
    return None


def _source_violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    violations: list[str] = []
    importlib_names = {"importlib"}
    import_module_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_names.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                violation = _module_violation(alias.name)
                if violation:
                    violations.append(
                        f"{path}:{node.lineno}: {violation}"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            violation = _module_violation(module)
            if violation:
                violations.append(
                    f"{path}:{node.lineno}: {violation}"
                )
            for alias in node.names:
                if alias.name in LEGACY_SYMBOLS:
                    violations.append(
                        f"{path}:{node.lineno}: legacy symbol {alias.name}"
                    )
        elif isinstance(node, ast.Call) and node.args:
            function = node.func
            is_import_module = (
                isinstance(function, ast.Name)
                and function.id in import_module_names
            ) or (
                isinstance(function, ast.Attribute)
                and function.attr == "import_module"
                and isinstance(function.value, ast.Name)
                and function.value.id in importlib_names
            )
            is_builtin_import = (
                isinstance(function, ast.Name) and function.id == "__import__"
            )
            module_arg = node.args[0]
            if (is_import_module or is_builtin_import) and isinstance(
                module_arg, ast.Constant
            ) and isinstance(module_arg.value, str):
                violation = _module_violation(module_arg.value)
                if violation:
                    violations.append(f"{path}:{node.lineno}: {violation}")
        if isinstance(node, ast.Name) and node.id in LEGACY_SYMBOLS:
            violations.append(f"{path}:{node.lineno}: legacy symbol {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in LEGACY_SYMBOLS:
            violations.append(f"{path}:{node.lineno}: legacy symbol {node.attr}")
    return violations


def _dependency_violations(pyproject: Path) -> list[str]:
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    dependencies = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        dependencies.extend(group)
    return [
        dependency
        for dependency in dependencies
        if re.sub(
            r"[-_.]+",
            "-",
            re.split(r"[<>=!~;\[\s]", dependency.strip(), maxsplit=1)[0],
        ).lower()
        == "openai-agents"
    ]


def _production_violations(backend: Path) -> list[str]:
    files = list((backend / "app").rglob("*.py"))
    files.extend((backend / "scripts").rglob("*.py"))
    files.append(backend / "main.py")
    return [item for path in files for item in _source_violations(path)] + [
        f"{backend / 'pyproject.toml'}: forbidden dependency {dependency}"
        for dependency in _dependency_violations(backend / "pyproject.toml")
    ]


def test_production_runtime_does_not_reference_openai_agents_sdk() -> None:
    backend = Path(__file__).resolve().parents[2]

    assert _production_violations(backend) == []


@pytest.mark.parametrize(
    "source,expected",
    (
        ("import agents", "forbidden import agents"),
        ("import agents.models", "forbidden import agents.models"),
        ("from agents import Agent", "forbidden import agents"),
        ("from agents.models import Model", "forbidden import agents.models"),
        ("from llm.agents_sdk import configure_agents_sdk", "legacy symbol configure_agents_sdk"),
        ("configure_agents_sdk()", "legacy symbol configure_agents_sdk"),
        ("runtime.configure_agents_sdk()", "legacy symbol configure_agents_sdk"),
        ("from analysis_agents import runner", "legacy symbol analysis_agents"),
        ('importlib.import_module("agents")', "forbidden import agents"),
        ('import importlib as il\nil.import_module("agents.models")', "forbidden import agents.models"),
        ('from importlib import import_module\nimport_module("agents")', "forbidden import agents"),
        ('from importlib import import_module as load\nload("analysis_agents")', "legacy symbol analysis_agents"),
        ('__import__("agents")', "forbidden import agents"),
    ),
)
def test_scanner_detects_sdk_and_legacy_references(
    tmp_path: Path, source: str, expected: str
) -> None:
    candidate = tmp_path / "example.py"
    candidate.write_text(source, encoding="utf-8")

    assert any(expected in violation for violation in _source_violations(candidate))


@pytest.mark.parametrize(
    "source",
    (
        "from agents.tiktok_video_analysis import AnalysisService",
        "import agents.tiktok_video_analysis as analysis",
        "from agents.tiktok_video_analysis.graph import build_analysis_graph",
        'importlib.import_module("agents.tiktok_video_analysis")',
        'from importlib import import_module as load\nload("agents.tiktok_video_analysis.graph")',
        "value = 'import agents'",
        "# configure_agents_sdk and analysis_agents\nvalue = 1",
        "def example():\n    '''configure_agents_sdk and analysis_agents documentation'''",
        "module_name = 'agents'\nimportlib.import_module(module_name)",
    ),
)
def test_scanner_allows_business_agents_package_and_plain_text(
    tmp_path: Path, source: str
) -> None:
    candidate = tmp_path / "example.py"
    candidate.write_text(source, encoding="utf-8")

    assert _source_violations(candidate) == []


@pytest.mark.parametrize(
    "dependency",
    (
        "openai-agents>=0.1",
        "openai_agents[dev]",
        "openai.agents~=0.2",
        "OpenAI-_.Agents",
    ),
)
def test_dependency_scanner_detects_openai_agents(
    tmp_path: Path, dependency: str
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\nname = 'example'\nversion = '1'\n"
        f"dependencies = [{dependency!r}]\n",
        encoding="utf-8",
    )

    assert _dependency_violations(pyproject) == [dependency]


@pytest.mark.parametrize(
    "dependency", ("openai-agent", "openai-agents-extra", "agents", "my-openai-agents")
)
def test_dependency_scanner_allows_other_package_names(
    tmp_path: Path, dependency: str
) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\nname = 'example'\nversion = '1'\n"
        f"dependencies = [{dependency!r}]\n",
        encoding="utf-8",
    )

    assert _dependency_violations(pyproject) == []
