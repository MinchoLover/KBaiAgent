#!/usr/bin/env python3
import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_FILES = (
    "app.py",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "run_mac.command",
    "run_windows.bat",
    "CHANGELOG.md",
    "START_HERE.md",
    "README.md",
    "ARCHITECTURE.md",
    "REFACTORING_REPORT.md",
    "prompts/system_prompt.md",
    "prompts/extraction_rules.md",
    "prompts/few_shot_examples.json",
    "prompts/adversarial_rules.md",
    "prompts/prompt_version.json",
    "dataset/manifest.jsonl",
    "knowledge_base/official_products.json",
    "scripts/evaluate_extraction.py",
    "scripts/run_regression.py",
    "scripts/export_finetuning_candidates.py",
    "scripts/export_finetuning_dataset.py",
    "docs/ARCHITECTURE.md",
    "docs/STAGE0_DOCUMENT_INTAKE.md",
    "docs/STAGE1_CONTRACT.md",
    "docs/STAGE2_CALCULATION_SPEC.md",
    "docs/STAGE3_OPTIMIZATION.md",
    "docs/STAGE4_RAG_POLICY.md",
    "docs/STAGE5_REPORT_POLICY.md",
    "docs/DATASET_AND_EVALS.md",
    "docs/SECURITY_PRIVACY.md",
    "docs/LIMITATIONS.md",
    "docs/DEMO_SCRIPT_KO.md",
    "docs/JUDGE_QA_KO.md",
    "docs/TEAM_HANDOFF.md",
    "docs/VALIDATION_REPORT.md",
    "samples/stage1_scenarios.json",
    "samples/sample_extraction.json",
    "samples/company_cashflow.json",
    "samples/expected_stage2.json",
    "samples/expected_stage3.json",
    "samples/expected_stage4.json",
    "samples/expected_report.json",
    "samples/expected_report.md",
    "reports/baseline_metrics.json",
    "reports/eval_summary.json",
    "reports/eval_report.md",
    "reports/failure_cases.jsonl",
    "artifacts/fine_tuning_candidate.jsonl",
    "artifacts/fine_tuning_excluded.jsonl",
)


def _run(command: List[str], env: Dict[str, str]) -> bool:
    print("$ {}".format(" ".join(command)))
    completed = subprocess.run(command, cwd=str(ROOT), env=env)
    return completed.returncode == 0


def _check_required_files(errors: List[str]) -> None:
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append("required file missing: {}".format(relative))


def _check_env_and_secrets(errors: List[str]) -> None:
    ignore_text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for required in (".env", ".venv/", "real_uploads/", ".cache/"):
        if required not in ignore_text:
            errors.append(".gitignore missing {}".format(required))
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    if not re.search(r"^OPENAI_API_KEY=$", example, re.MULTILINE):
        errors.append(".env.example must keep OPENAI_API_KEY empty")
    for variable in (
        "STAGE1_ALLOW_PRIVATE_ENDPOINTS",
        "STAGE1_ALLOWED_HOSTS",
        "OFFICIAL_SEARCH_CACHE_TTL_HOURS",
        "OFFICIAL_DOMAINS",
    ):
        if not re.search(
            r"^{}=".format(variable),
            example,
            re.MULTILINE,
        ):
            errors.append(
                ".env.example missing security setting {}".format(
                    variable
                )
            )

    secret_pattern = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")
    roots = [
        ROOT / "app.py",
        ROOT / "src",
        ROOT / "scripts",
        ROOT / "prompts",
        ROOT / "knowledge_base",
    ]
    for source in roots:
        paths = [source] if source.is_file() else list(source.rglob("*"))
        for path in paths:
            if not path.is_file() or path.suffix not in {
                ".py",
                ".md",
                ".json",
            }:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if secret_pattern.search(text):
                errors.append("possible API secret in {}".format(path))


def _check_prompts_and_schema(errors: List[str]) -> None:
    from prompt import build_system_prompt, load_few_shot_examples
    from schemas import TradeDocumentExtraction

    prompt = build_system_prompt().lower()
    for phrase in ("데이터", "추측", "evidence"):
        if phrase not in prompt:
            errors.append("prompt policy missing phrase: {}".format(phrase))
    examples = load_few_shot_examples()
    if len(examples) < 10:
        errors.append("few-shot examples must be at least 10")
    for index, example in enumerate(examples):
        output = example.get(
            "expected_output",
            example.get("output", example.get("assistant_output")),
        )
        try:
            TradeDocumentExtraction.model_validate(output)
        except Exception as exc:
            errors.append(
                "few-shot {} schema invalid: {}".format(index + 1, exc)
            )


def _check_readme(errors: List[str]) -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    commands = (
        "python -m streamlit run app.py",
        "python -m unittest discover -s tests -v",
        "python scripts/evaluate_extraction.py --mode offline",
        "python scripts/run_regression.py",
        "python scripts/verify.py",
    )
    for command in commands:
        if command not in readme:
            errors.append("README command missing: {}".format(command))
    for document in ("ARCHITECTURE.md", "REFACTORING_REPORT.md"):
        if document not in readme:
            errors.append("README document link missing: {}".format(document))


def _check_demo(errors: List[str]) -> None:
    from src.demo import run_offline_demo

    result = run_offline_demo()
    if not result["validation"].stage2_allowed:
        errors.append("offline demo confirmation gate is closed")
    if not result["stage2"].scenario_results:
        errors.append("offline demo has no scenario results")
    if len(result["stage3"].candidates) != 3:
        errors.append("offline demo must have three strategy candidates")
    if not result["stage4"].candidates:
        errors.append("offline demo has no official KB candidates")
    report_numbers = result["stage2"].base_required_or_proceeds_krw
    if report_numbers not in result["report"].markdown:
        errors.append("offline report lost Stage 2 base flow trace")
    workflow = result.get("workflow_state")
    if workflow is None:
        errors.append("offline demo has no WorkflowState")
        return
    if workflow.final_status.value != "SUCCEEDED":
        errors.append("offline workflow did not succeed")
    stage_names = [item.stage for item in workflow.trace]
    if stage_names != [
        "intake",
        "market_risk",
        "cashflow",
        "hedge",
        "product_search",
        "report",
    ]:
        errors.append("offline workflow trace order is invalid")
    if not workflow.critic_result or not workflow.critic_result.passed:
        errors.append("offline workflow critic did not pass")


def _check_output_schemas(errors: List[str]) -> None:
    from schemas import TradeDocumentExtraction
    from src.domain.product_models import Stage4Result
    from src.domain.report_models import ReportResult
    from src.domain.stage1_models import NormalizedScenarioSet
    from src.domain.stage2_models import Stage2Input, Stage2Result
    from src.domain.stage3_models import Stage3Result

    contracts = (
        ("samples/sample_extraction.json", TradeDocumentExtraction),
        ("samples/stage1_scenarios.json", NormalizedScenarioSet),
        ("samples/company_cashflow.json", Stage2Input),
        ("samples/expected_stage2.json", Stage2Result),
        ("samples/expected_stage3.json", Stage3Result),
        ("samples/expected_stage4.json", Stage4Result),
        ("samples/expected_report.json", ReportResult),
    )
    for relative, model in contracts:
        try:
            payload = json.loads(
                (ROOT / relative).read_text(encoding="utf-8")
            )
            model.model_validate(payload)
        except Exception as exc:
            errors.append(
                "output schema invalid {}: {}".format(
                    relative,
                    type(exc).__name__,
                )
            )


def _check_imports(errors: List[str]) -> None:
    modules = (
        "schemas",
        "validators",
        "src.config",
        "src.document_intake.extractor",
        "src.document_intake.openai_adapter",
        "src.application.demo_service",
        "src.application.stage2_input_service",
        "src.security.upload_guard",
        "src.stage1.adapter",
        "src.stage2.engine",
        "src.stage3.optimizer",
        "src.stage4.local_kb",
        "src.stage4.official_search",
        "src.stage5.report_agent",
        "src.ui.state",
        "src.workflow.gates",
        "src.workflow.orchestrator",
        "src.workflow.result",
        "src.workflow.state",
        "src.workflow.trace",
    )
    for module in modules:
        try:
            importlib.import_module(module)
        except Exception as exc:
            errors.append(
                "import failed {}: {}".format(module, type(exc).__name__)
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    errors: List[str] = []
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = "/tmp/invoice_intake_verify_pycache"

    _check_required_files(errors)
    _check_env_and_secrets(errors)
    _check_prompts_and_schema(errors)
    _check_readme(errors)
    _check_imports(errors)
    _check_output_schemas(errors)
    _check_demo(errors)

    compile_ok = _run(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "-x",
            r"(^|/)(\.venv|\.git|__pycache__)(/|$)",
            ".",
        ],
        env,
    )
    if not compile_ok:
        errors.append("compileall failed")
    if not args.skip_tests:
        tests_ok = _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ],
            env,
        )
        if not tests_ok:
            errors.append("unit tests failed")

    if errors:
        print("\nVERIFY FAILED")
        for error in errors:
            print("- {}".format(error))
        return 1
    print("\nVERIFY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
