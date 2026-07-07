from __future__ import annotations

from pathlib import Path

from ..schemas import DiagnosisResult, DiagnosticBundle


def _code_hint(code_roots: list[Path], relative_path: str) -> str:
    for root in code_roots:
        candidate = root / relative_path
        if candidate.is_file():
            return f" in {candidate}"
    if code_roots:
        return f" under {code_roots[0]}"
    return ""


class StubAICliAdapter:
    async def diagnose(
        self,
        *,
        bundle: DiagnosticBundle,
        code_roots: list[Path],
        prompt_template: str,
    ) -> DiagnosisResult:
        state = bundle.health.get("state", "UNKNOWN")
        last_error = (bundle.health.get("last_error") or "").lower()
        actual = bundle.health.get("actual") or {}
        exit_code = actual.get("exit_code")
        log_snippet = (actual.get("log_snippet") or "").lower()

        if state == "READY" and not last_error:
            return DiagnosisResult(
                verdict="operator_actionable",
                summary="The appliance reports a healthy ready state. If you are still seeing issues, describe the symptoms in more detail.",
                confidence="medium",
                recommended_actions=[
                    "Confirm the issue still occurs after refreshing this page.",
                    "Note the exact time and action that triggered the problem.",
                    "Send another report if the state changes to degraded.",
                ],
                evidence=["health.state=READY"],
            )

        oom_signals = ("out of memory", "oom", "cuda", "insufficient")
        if any(sig in last_error or sig in log_snippet for sig in oom_signals):
            return DiagnosisResult(
                verdict="operator_actionable",
                summary="Diagnostics suggest a resource constraint, often caused by model size or GPU allocation relative to available memory.",
                confidence="high",
                recommended_actions=[
                    "Reduce model parallelism or choose a smaller quantization.",
                    "Free GPU capacity by disabling unused deployments.",
                    "Verify each node has enough VRAM for the enabled model.",
                ],
                engineering_notes="Matched OOM/GPU resource heuristics in last_error or log_snippet.",
                evidence=[f"health.state={state}", f"exit_code={exit_code}"],
            )

        if state == "DEGRADED" and exit_code not in (None, 0):
            code_hint = _code_hint(code_roots, "inferedge-phase1/controller/reconciler.py")
            return DiagnosisResult(
                verdict="likely_bug",
                summary="A runtime process exited unexpectedly while the appliance was reconciling. This pattern often indicates a product defect when configuration appears valid.",
                confidence="medium",
                recommended_actions=[
                    "Capture the time of failure and keep the appliance powered on.",
                    "Avoid repeated config changes until support analysis completes.",
                    "Contact vendor support if the issue persists after a reboot.",
                ],
                engineering_notes=(
                    f"Non-zero exit_code={exit_code} with state=DEGRADED. "
                    f"Inspect reconciler exit handling{code_hint}."
                ),
                evidence=[f"health.state={state}", f"exit_code={exit_code}"],
            )

        if last_error:
            return DiagnosisResult(
                verdict="operator_actionable",
                summary="The controller reported a reconciliation error that may be resolved by adjusting configuration or cluster topology.",
                confidence="medium",
                recommended_actions=[
                    "Review recent configuration changes on the Orchestration and Models pages.",
                    "Check that all nodes are online and the head node is reachable.",
                    f"Investigate: {bundle.health.get('last_error')}",
                ],
                evidence=[f"health.last_error present", f"health.state={state}"],
            )

        return DiagnosisResult(
            verdict="insufficient_data",
            summary="Not enough diagnostic signal to classify this issue. Add a note describing what you expected versus what happened.",
            confidence="low",
            recommended_actions=[
                "Describe the steps that led to the issue in the note field.",
                "Send the report again after reproducing the problem.",
            ],
            evidence=[f"health.state={state}"],
        )