"""Opt-in real-model evaluator for the evidence-first latest analysis contract.

Run only interactively with an explicit media path, route, and model
configuration. It never runs from pytest, import-time hooks, or CI, and
prints only summarized statuses and durations (no secrets or media evidence).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
for path in (BACKEND_ROOT / "app", BACKEND_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from agents.tiktok_video_analysis import AnalysisService, JsonResultStore, MediaBoundary
from llm.model_factory import _create_chat_model
from models.results import AnalysisRequest, AnalysisResult
from worker.video_analysis import load_prompt

FORBIDDEN_GENERATION_FIELDS = ("ai_video_prompt", "iteration", "post_production")
ABSOLUTE_PATH_MARKERS = ("C:\\", "c:\\", ":/", "\\private\\", "/private/", "file://")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用真实模型评估 latest 证据契约并校验结果",
    )
    parser.add_argument("--media", required=True, help="本地视频文件路径或 URL")
    parser.add_argument(
        "--route",
        choices=("R", "G", "none"),
        default="none",
        help="显式评审路线：R / G / none（none 只评 C）",
    )
    parser.add_argument("--model", required=True, help="LiteLLM 模型名")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("EVAL_LLM_API_KEY"),
        help="模型 API key（缺省读 EVAL_LLM_API_KEY）",
    )
    parser.add_argument("--api-base", default=None, help="模型 API base URL（可选）")
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--output", required=True, help="结果 JSON 输出路径")
    return parser


def _iter_json_keys(node) -> object:
    if isinstance(node, dict):
        yield from node
        for value in node.values():
            yield from _iter_json_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_keys(item)


def _iter_json_strings(node) -> object:
    if isinstance(node, str):
        yield node
    elif isinstance(node, list):
        for item in node:
            yield from _iter_json_strings(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_json_strings(value)


def _selected_dimensions(result: AnalysisResult) -> list:
    evaluation = result.evaluation
    selected = list(evaluation.common_score_c.dimensions)
    if evaluation.review_route == "R" and evaluation.specialized_score_r is not None:
        selected.extend(evaluation.specialized_score_r.dimensions)
    elif evaluation.review_route == "G" and evaluation.specialized_score_g is not None:
        selected.extend(evaluation.specialized_score_g.dimensions)
    return selected


def _contract_errors(result: AnalysisResult, expected_route: str | None) -> list[str]:
    errors: list[str] = []
    evaluation = result.evaluation
    if result.meta.schema_version != "v4.0":
        errors.append("schema_version must be v4.0")
    if result.decision.recommended_grade is not None:
        errors.append("recommended_grade must stay null")
    if result.evidence_card.official_scoring_ready is not False:
        errors.append("official_scoring_ready must stay false")
    if evaluation.review_route != expected_route:
        errors.append(
            f"review route mismatch: {evaluation.review_route} != {expected_route}"
        )
    if (
        evaluation.specialized_score_r is not None
        and evaluation.specialized_score_g is not None
    ):
        errors.append("R and G score sections must be mutually exclusive")
    if evaluation.review_route is None:
        if evaluation.diagnostic_total is not None:
            errors.append("C-only route must not expose a diagnostic total")
    else:
        all_scorable = all(dimension.scorable for dimension in _selected_dimensions(result))
        if all_scorable and evaluation.diagnostic_total != evaluation.partial_points:
            errors.append("all dimensions scorable but diagnostic total missing")
        if not all_scorable and evaluation.diagnostic_total is not None:
            errors.append("unscorable dimensions must not expose a diagnostic total")

    payload = result.model_dump(mode="json")
    forbidden = [
        key for key in _iter_json_keys(payload) if key in FORBIDDEN_GENERATION_FIELDS
    ]
    if forbidden:
        errors.append(f"forbidden generation fields present: {sorted(set(forbidden))}")
    for value in _iter_json_strings(payload):
        if any(marker in value for marker in ABSOLUTE_PATH_MARKERS):
            errors.append("result contains an absolute path")
            break
    if result.evidence_card.source_id != f"sha256:{result.evidence_card.source_sha256}":
        errors.append("source id is not derived from the canonical sha256")
    return errors


def _summarize(result: AnalysisResult) -> dict:
    timings = result.meta.timings
    return {
        "status": "ok",
        "schema_version": result.meta.schema_version,
        "gate": result.decision.gate_status.value,
        "scoring_status": result.decision.scoring_status.value,
        "route": result.evaluation.review_route,
        "diagnostic_total": result.evaluation.diagnostic_total,
        "partial_points": result.evaluation.partial_points,
        "partial_max_points": result.evaluation.partial_max_points,
        "conflict_count": len(result.evaluation.evidence_conflicts),
        "timings_ms": timings.model_dump() if timings is not None else None,
    }


async def evaluate(args: argparse.Namespace) -> int:
    if os.environ.get("CI") or os.environ.get("PYTEST_CURRENT_TEST"):
        print("拒绝在 CI 或 pytest 环境中运行评估器", file=sys.stderr)
        return 2
    if not args.api_key:
        print("缺少 --api-key（或 EVAL_LLM_API_KEY）", file=sys.stderr)
        return 2
    if not Path(args.media).is_file():
        print(f"媒体文件不存在：{args.media}", file=sys.stderr)
        return 2

    model = _create_chat_model(
        model=args.model,
        api_key=args.api_key,
        api_base=args.api_base,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        enable_thinking=None,
    )
    service = AnalysisService(
        media=MediaBoundary(),
        model=model,
        store=JsonResultStore(),
        prompt_loader=load_prompt,
    )
    route = None if args.route == "none" else args.route
    request = AnalysisRequest(
        source=args.media,
        model=args.model,
        api_key=args.api_key,
        base_url=args.api_base,
        review_route=route,
        output_path=Path(args.output),
    )
    result = await service.run(request)

    errors = _contract_errors(result, route)
    summary = _summarize(result)
    summary["status"] = "ok" if not errors else "failed"
    print(json.dumps(summary, ensure_ascii=False))
    for error in errors:
        print(f"CONTRACT FAIL: {error}", file=sys.stderr)
    return 0 if not errors else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        exit_code = asyncio.run(evaluate(args))
    except Exception as exc:
        print(f"评估失败：{type(exc).__name__}", file=sys.stderr)
        exit_code = 2
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()


