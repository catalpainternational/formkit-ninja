"""
Pipeline helpers for code generation.

This module provides a minimal pipeline abstraction so generation steps can be
composed and reused without inflating CodeGenerator.generate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, List, Protocol, Union

from formkit_ninja.formkit_schema import FormKitSchema

if TYPE_CHECKING:
    from formkit_ninja.parser.generator import CodeGenerator

SchemaInput = Union[List[dict], FormKitSchema]


@dataclass
class GenerationContext:
    """State container for code generation steps."""

    schema: SchemaInput
    generator: "CodeGenerator"
    data: dict[str, Any] = field(default_factory=dict)


class GenerationStep(Protocol):
    """Protocol for pipeline steps."""

    def run(self, context: GenerationContext) -> None:
        """Execute a generation step."""


class CallableStep:
    """Adapter to use simple callables as pipeline steps."""

    def __init__(self, func: Callable[[GenerationContext], None]) -> None:
        self.func = func

    def run(self, context: GenerationContext) -> None:
        self.func(context)


class GenerationPipeline:
    """Execute a list of steps in order."""

    def __init__(self, steps: list[GenerationStep]) -> None:
        self.steps = steps

    def run(self, context: GenerationContext) -> None:
        for step in self.steps:
            step.run(context)
