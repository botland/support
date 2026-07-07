from __future__ import annotations

from pathlib import Path

from src.ai.prompt import load_prompt_template, render_prompt
from src.schemas import DiagnosticBundle, SoftwareVersions, TopologySummary


def test_render_prompt_includes_bundle_and_roots():
    template = "bundle:\n{bundle_json}\nroots:\n{code_roots}\nnote:\n{user_note}"
    bundle = DiagnosticBundle(
        appliance_id="a1",
        submitted_at="2026-07-07T12:00:00Z",
        software=SoftwareVersions(),
        topology=TopologySummary(
            serving_mode="standalone",
            role="standalone",
            node_count=1,
            local_node_id="node-1",
        ),
        health={"state": "READY", "last_error": None},
        user_note="help",
    )
    rendered = render_prompt(
        template=template,
        bundle=bundle,
        code_roots=[Path("/code/inferedge")],
    )
    assert '"appliance_id": "a1"' in rendered
    assert "/code/inferedge" in rendered
    assert "help" in rendered


def test_load_default_prompt_template():
    text = load_prompt_template()
    assert "{bundle_json}" in text
    assert "likely_bug" in text