"""Visual capability selection remains explicit and budget-aware."""
from types import SimpleNamespace

import pytest

from core.action_loader import strip_meta
from core.visual_guidance import guidance
from plugins.present_content import PLUGIN as NARRATIVE
from plugins.visualize_data import PLUGIN as CHART
from providers import schema
from providers.engine_pipeline import PipelineEngine
from providers.llm_openai import OpenAICompatLLM


def decl(name):
    return {'name': name, 'description': 'x', 'parameters': {'type': 'OBJECT', 'properties': {}}}


def names(decls):
    return [d['name'] for d in decls]


def test_opt_in_budget_prefers_only_existing_enabled_tools_and_preserves_order():
    all_tools = [decl('open_app'), decl('undo'), NARRATIVE, CHART]
    assert names(schema.budget(all_tools, max_tools=2)) == ['open_app', 'undo']
    selected = schema.budget(all_tools, max_tools=2, preferred_names=schema.VISUAL_TOOLS)
    assert names(selected) == ['present_content', 'visualize_data']
    assert schema.budget(all_tools, preferred_names=schema.VISUAL_TOOLS) == all_tools
    missing = [decl('open_app'), CHART]
    assert names(schema.budget(missing, max_tools=1, preferred_names=schema.VISUAL_TOOLS)) == ['visualize_data']
    assert names(schema.budget([decl('open_app')], max_tools=1,
                               preferred_names=schema.VISUAL_TOOLS)) == ['open_app']


def test_priority_respects_character_budget_and_two_stage_budgeting():
    all_tools = [decl('open_app'), decl('undo'), NARRATIVE, CHART]
    limit = schema.payload_size([NARRATIVE, CHART])
    first = schema.budget(all_tools, max_tools=2, max_chars=limit, preferred_names=schema.VISUAL_TOOLS)
    assert names(first) == ['present_content', 'visualize_data']
    assert schema.payload_size(first) <= limit
    llm = SimpleNamespace(caps={'tools': True, 'tool_format': 'openai', 'max_tools': 2,
                                'max_tool_chars': limit, 'prioritize_visual_tools': True})
    engine = PipelineEngine(llm, config=SimpleNamespace(tools=[{'function_declarations': strip_meta(first)}]))
    assert names(engine._declarations) == names(first)
    assert [t['function']['name'] for t in engine._tools] == names(first)


@pytest.mark.parametrize('value, expected', [('', False), ('0', False), ('false', False),
                                             ('1', True), ('true', True), (True, True)])
def test_openai_compatible_opt_in_must_be_explicit(value, expected):
    llm = OpenAICompatLLM({'base_url': 'http://127.0.0.1:11434/v1',
                           'prioritize_visual_tools': value})
    assert llm.caps['prioritize_visual_tools'] is expected


def test_guidance_mentions_only_offered_tools_and_does_not_promise_automation():
    assert guidance([]) == ''
    text = guidance(['present_content'])
    assert 'present_content' in text and 'visualize_data' not in text
    assert 'not automatically synchronized' in text
    text = guidance(['visualize_data'])
    assert 'visualize_data' in text and 'present_content' not in text
    assert 'actually supplied' in text and 'declines' in text
