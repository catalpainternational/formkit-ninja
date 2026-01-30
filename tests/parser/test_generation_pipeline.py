import pytest

from formkit_ninja.parser.generation_pipeline import CallableStep, GenerationContext, GenerationPipeline


class DummyGenerator:
    pass


def test_pipeline_runs_steps_in_order() -> None:
    calls: list[str] = []

    def step_one(context: GenerationContext) -> None:
        calls.append("one")

    def step_two(context: GenerationContext) -> None:
        calls.append("two")

    pipeline = GenerationPipeline([CallableStep(step_one), CallableStep(step_two)])
    context = GenerationContext(schema=[], generator=DummyGenerator())

    pipeline.run(context)

    assert calls == ["one", "two"]


def test_pipeline_stops_on_exception() -> None:
    calls: list[str] = []

    def step_one(context: GenerationContext) -> None:
        calls.append("one")

    def step_two(context: GenerationContext) -> None:
        calls.append("two")
        raise RuntimeError("boom")

    def step_three(context: GenerationContext) -> None:
        calls.append("three")

    pipeline = GenerationPipeline([CallableStep(step_one), CallableStep(step_two), CallableStep(step_three)])
    context = GenerationContext(schema=[], generator=DummyGenerator())

    with pytest.raises(RuntimeError, match="boom"):
        pipeline.run(context)

    assert calls == ["one", "two"]
