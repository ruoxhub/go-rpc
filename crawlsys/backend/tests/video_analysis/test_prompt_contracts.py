import re
from pathlib import Path

import pytest


PROMPT_DIR = Path(__file__).parents[2] / "app" / "prompt"

EXPECTED_G0_FAILURES = {
    "颜色/长度/版型/关键结构漂移",
    "Logo/图案/抽绳/口袋/拉链增减",
    "无后袋生成后袋",
    "正背面冲突",
    "衣物层级粘连",
    "关键展示完全遮挡",
    "把未知性能写成已证明事实",
    "换脸/体型/纹身大幅漂移",
    "多肢/手指畸形/穿透",
    "动作缺少释放或恢复",
    "人物/车辆/宠物穿模",
    "面料异常材质或撕裂",
    "一镜到底发生状态重置",
    "关键动作/镜头缺失",
    "时长不符",
    "严重闪屏/黑帧/虚焦/过曝",
    "错误文字/水印/品牌",
    "不露脸要求被破坏",
}

EXPECTED_DIMENSIONS = {
    ("C1", "受众与购买需求", 6),
    ("C2", "钩子停留能力", 10),
    ("C3", "商品识别与曝光", 6),
    ("C4", "卖点选择", 8),
    ("C5", "可见证据链", 12),
    ("C6", "节奏与信息密度", 8),
    ("C7", "记忆点与商品绑定", 6),
    ("C8", "信任、顾虑与行动", 4),
    ("R1", "时间线与结构可拆解性", 8),
    ("R2", "AI 复刻友好度", 10),
    ("R3", "可迁移变量丰富度", 8),
    ("R4", "换成我方商品的安全性", 6),
    ("R5", "生产成本与稳定性", 4),
    ("R6", "差异化潜力", 4),
    ("G1", "商品一致性", 12),
    ("G2", "人物身份与服装层级", 5),
    ("G3", "动作完整性与力量感", 8),
    ("G4", "物理、接触与回弹", 6),
    ("G5", "镜头与构图连续性", 4),
    ("G6", "技术画质", 3),
    ("G7", "背景、灯光与声音联动", 2),
}

OBSERVATION_SECTION_CLAUSES = (
    "禁止评分、分数、G0 结论或任何 C/R/G 评审；",
    "禁止等级、正式结论或排名；",
    "禁止审批、发布、通过/拒绝或 Owner 决策；",
    "禁止生成创意 Prompt、改写脚本或复刻方案；",
    "禁止迭代、修正建议或优化计划；",
    "禁止后期制作输出，包括字幕稿、旁白、配乐、音效、剪辑或平台适配建议。",
)

REVIEW_SECTION_CLAUSES = (
    "禁止同时输出 R 和 G；",
    "禁止 formal grade、正式等级、排名或最终审批；",
    "禁止以高分覆盖、弱化或绕过 G0；",
    "禁止创意生成，包括生成视频 Prompt、脚本、复刻方案或改写建议；",
    "禁止迭代或修正计划；禁止后期制作输出，包括字幕稿、旁白、配乐、音效、剪辑或平台适配建议。",
)

LEGACY_V2_MIXED_APPENDIX = """
## v2 mixed responsibilities
执行十四维评分并给出审批等级。
生成创意 Prompt，进行迭代，并输出后期制作建议。
同时输出 R 和 G，以高分覆盖 G0，并给出 formal grade。
"""

OBSERVATION_AFFIRMATIVE_PATTERNS = (
    r"执行\s*评分",
    r"评分.{0,4}审批",
    r"给出\s*(?:正式)?等级",
    r"(?:给出|执行|作出|输出).{0,6}审批",
    r"生成\s*创意\s*prompt",
    r"(?:进行|执行|负责|提供).{0,4}迭代(?:建议)?",
    r"(?:输出|提供|负责|制定).{0,4}后期制作(?:建议|计划)?|后期制作建议",
)

REVIEW_AFFIRMATIVE_PATTERNS = (
    r"同时\s*输出\s*r\s*和\s*g",
    r"(?:给出\s*)?formal\s*grade",
    r"(?:允许|使用|用|让).{0,6}高分.{0,6}(?:覆盖|抵消).{0,6}g0",
    r"创意\s*生成",
    r"(?:进行|执行|负责|提供).{0,4}迭代(?:建议)?",
    r"(?:输出|提供|负责|制定).{0,4}后期制作(?:建议|计划)?|后期制作建议",
)


def _read_prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def _assert_contains(prompt: str, *terms: str) -> None:
    missing = [term for term in terms if term not in prompt]
    assert not missing, f"prompt missing required contract terms: {missing}"


def _extract_strict_prohibition_section(prompt: str) -> str:
    headings = list(re.finditer(r"^## 严格禁止\s*$", prompt, re.MULTILINE))
    assert len(headings) == 1, "prompt must contain exactly one required prohibition section"
    content_start = headings[0].end()
    next_heading = re.search(r"^## (?!#)", prompt[content_start:], re.MULTILINE)
    content_end = (
        content_start + next_heading.start() if next_heading is not None else len(prompt)
    )
    section = prompt[content_start:content_end].strip()
    assert section, "required prohibition section must not be empty"
    return section


def _move_clause_outside_strict_section(prompt: str, clause: str) -> str:
    heading = re.search(r"^## 严格禁止\s*$", prompt, re.MULTILINE)
    assert heading is not None
    content_start = heading.end()
    next_heading = re.search(r"^## (?!#)", prompt[content_start:], re.MULTILINE)
    content_end = (
        content_start + next_heading.start() if next_heading is not None else len(prompt)
    )
    section = prompt[content_start:content_end]
    bullet = f"- {clause}"
    assert section.count(bullet) == 1
    section_without_clause = section.replace(bullet, "", 1)
    outside_duplicate = f"\n## 合同外重复样本\n{bullet}\n"
    return (
        prompt[:content_start]
        + section_without_clause
        + prompt[content_end:]
        + outside_duplicate
    )


def _assert_required_prohibitions(prompt: str, clauses: tuple[str, ...]) -> None:
    section = _extract_strict_prohibition_section(prompt)
    actual_clauses = {
        re.sub(r"\s+", " ", line.removeprefix("- ")).casefold()
        for line in section.splitlines()
        if line.startswith("- ")
    }
    missing = [
        clause
        for clause in clauses
        if re.sub(r"\s+", " ", clause).casefold() not in actual_clauses
    ]
    assert not missing, f"prompt missing required prohibition clauses: {missing}"


def _assert_no_affirmative_duties(prompt: str, patterns: tuple[str, ...]) -> None:
    violations = []
    for pattern in patterns:
        for match in re.finditer(pattern, prompt, re.IGNORECASE):
            line_start = prompt.rfind("\n", 0, match.start()) + 1
            binding_prefix = prompt[line_start : match.start()]
            if not re.search(r"(?:禁止|不得)\s*$", binding_prefix):
                violations.append(match.group(0))
    assert not violations, f"prompt adds forbidden duties: {violations}"


def _assert_no_schema_or_numeric_anchor(prompt: str) -> None:
    assert not re.search(r"```(?:json)?\s*[\[{]", prompt, re.IGNORECASE)
    assert not re.search(r'^\s*(?:\{\s*"|\[\s*\{)', prompt, re.MULTILINE)
    assert not re.search(r'"type"\s*:\s*"(?:object|array)"', prompt, re.IGNORECASE)
    assert not re.search(r'"(?:properties|items)"\s*:', prompt, re.IGNORECASE)
    assert not re.search(
        r'["\']?(?:awarded_points|confidence|score)["\']?\s*'
        r'(?:(?:的\s*)?值\s*|value\s*)?'
        r'(?:=|:|为|是|is|equals?|of|to)\s*-?\d+(?:\.\d+)?',
        prompt,
        re.IGNORECASE,
    )
    assert not re.search(
        r"(?:评分|置信度)\s*(?:=|:|为)\s*\d+(?:\.\d+)?(?:\s*分)?",
        prompt,
    )


def _extract_review_contract(prompt: str) -> tuple[set[str], set[tuple[str, str, int]]]:
    g0_failures = set(re.findall(r"^- \[G0\] (.+)$", prompt, re.MULTILINE))
    dimensions = {
        (dimension_id, name, int(max_points))
        for dimension_id, name, max_points in re.findall(
            r"^- \[(?:C|R|G)\] ([CRG]\d+) \| (.+?) \| 上限 (\d+)$",
            prompt,
            re.MULTILINE,
        )
    }
    return g0_failures, dimensions


def _validate_observation_prompt(prompt: str) -> None:
    _assert_required_prohibitions(prompt, OBSERVATION_SECTION_CLAUSES)
    _assert_no_affirmative_duties(prompt, OBSERVATION_AFFIRMATIVE_PATTERNS)
    _assert_contains(
        prompt,
        "仅事实观察",
        "证据优先级",
        "FULL_VIDEO",
        "SAMPLED_FRAMES",
        "未观察区间",
        "自适应 Timeline",
        "0.5 秒",
        "0.25 秒",
        "POSITIONING",
        "FORCE",
        "PEAK",
        "FEEDBACK",
        "RELEASE",
        "RECOVERY",
        "claim -> product_structure -> demonstration_action -> visible_feedback -> usage_result -> user_benefit",
        "商业逻辑八问",
        "缺陷",
        "TRANSCRIPT/OCR/subtitles",
        "不可信线索",
        "画面或声音交叉验证",
        "内容分类",
        "视频拓扑",
        "不得推断",
        "ObservationResult",
        "只返回",
    )
    _assert_no_schema_or_numeric_anchor(prompt)


def _validate_review_prompt(prompt: str) -> None:
    _assert_required_prohibitions(prompt, REVIEW_SECTION_CLAUSES)
    _assert_no_affirmative_duties(prompt, REVIEW_AFFIRMATIVE_PATTERNS)
    _assert_contains(
        prompt,
        "原始媒体",
        "第一阶段 ObservationResult JSON ledger",
        "必须重新查看原始媒体",
        "supplemental_evidence",
        "evidence_conflicts",
        "review_route",
        "None = C-only",
        "R/G 二选一",
        "G0 优先",
        "不能被高分覆盖",
        "C + 选中的 R/G",
        "R4",
        "G1",
        "不可评分",
        "NOT_PROVIDED",
        "partial_points",
        "partial_max_points",
        "不得归一化",
        "Python",
        "PROVISIONAL",
        "Owner review",
        "EvaluationDraft",
        "只返回",
        "TRANSCRIPT/OCR/subtitles",
        "不可信线索",
        "约束上限",
        "不是数值评分示例",
    )
    g0_failures, dimensions = _extract_review_contract(prompt)
    assert g0_failures == EXPECTED_G0_FAILURES
    assert dimensions == EXPECTED_DIMENSIONS
    _assert_no_schema_or_numeric_anchor(prompt)


def test_observation_prompt_satisfies_contract() -> None:
    _validate_observation_prompt(_read_prompt("tiktok_video_observation.md"))


def test_review_prompt_satisfies_contract() -> None:
    _validate_review_prompt(_read_prompt("tiktok_video_analysis.md"))


@pytest.mark.parametrize(
    ("name", "validator"),
    [
        ("tiktok_video_observation.md", _validate_observation_prompt),
        ("tiktok_video_analysis.md", _validate_review_prompt),
    ],
)
def test_validator_rejects_prompt_without_strict_prohibition_section(
    name: str,
    validator,
) -> None:
    prompt_without_section = _read_prompt(name).split("## 严格禁止", maxsplit=1)[0]
    with pytest.raises(AssertionError, match="required prohibition"):
        validator(prompt_without_section)


@pytest.mark.parametrize(
    ("name", "validator", "clause"),
    [
        *[
            ("tiktok_video_observation.md", _validate_observation_prompt, clause)
            for clause in OBSERVATION_SECTION_CLAUSES
        ],
        *[
            ("tiktok_video_analysis.md", _validate_review_prompt, clause)
            for clause in REVIEW_SECTION_CLAUSES
        ],
    ],
)
def test_validator_rejects_each_clause_removed_from_strict_section(
    name: str,
    validator,
    clause: str,
) -> None:
    mutated = _move_clause_outside_strict_section(_read_prompt(name), clause)
    assert mutated.count(clause) == 1, "mutation must keep the full clause outside the section"
    with pytest.raises(AssertionError, match="required prohibition"):
        validator(mutated)


@pytest.mark.parametrize(
    ("suffix", "expected_error"),
    [
        ("\n## 严格禁止\n- 禁止评分。\n", "exactly one"),
        ("\n## 严格禁止\n", "exactly one"),
    ],
)
def test_validator_rejects_duplicate_strict_prohibition_section(
    suffix: str,
    expected_error: str,
) -> None:
    with pytest.raises(AssertionError, match=expected_error):
        _validate_observation_prompt(_read_prompt("tiktok_video_observation.md") + suffix)


def test_validator_rejects_empty_strict_prohibition_section() -> None:
    prompt = _read_prompt("tiktok_video_analysis.md")
    empty_section = re.sub(
        r"(?ms)^## 严格禁止\s*$.*\Z",
        "## 严格禁止\n",
        prompt,
    )
    with pytest.raises(AssertionError, match="must not be empty"):
        _validate_review_prompt(empty_section)


@pytest.mark.parametrize(
    "appendix",
    [
        "执行评分并给出等级。",
        "给出审批结论。",
        "生成创意 Prompt。",
        "进行迭代。",
        "输出后期制作建议。",
    ],
)
def test_observation_validator_rejects_appended_mixed_responsibility(appendix: str) -> None:
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_observation_prompt(_read_prompt("tiktok_video_observation.md") + appendix)


def test_observation_validator_rejects_negation_bound_to_omission_not_duty() -> None:
    appendix = "禁止遗漏：执行评分并给出审批结论。"
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_observation_prompt(_read_prompt("tiktok_video_observation.md") + appendix)


@pytest.mark.parametrize(
    "appendix",
    [
        "禁止遗漏评分审批。",
        "提供迭代建议。",
        "制定后期制作计划。",
    ],
)
def test_observation_validator_rejects_additional_duty_variants(appendix: str) -> None:
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_observation_prompt(_read_prompt("tiktok_video_observation.md") + appendix)


@pytest.mark.parametrize(
    "appendix",
    [
        "同时输出 R 和 G。",
        "给出 formal grade。",
        "允许高分覆盖 G0。",
        "负责创意生成。",
        "进行迭代并输出后期制作建议。",
        "提供迭代建议。",
        "制定后期制作计划。",
    ],
)
def test_review_validator_rejects_appended_forbidden_responsibility(appendix: str) -> None:
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_review_prompt(_read_prompt("tiktok_video_analysis.md") + appendix)


def test_review_validator_rejects_negation_bound_to_rejection_not_duty() -> None:
    appendix = "不得拒绝：同时输出 R 和 G，并给出 formal grade。"
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_review_prompt(_read_prompt("tiktok_video_analysis.md") + appendix)


def test_directly_bound_prohibitions_are_valid_for_finite_duty_rules() -> None:
    _assert_no_affirmative_duties(
        "禁止执行评分。不得给出审批结论。禁止提供迭代建议。不得制定后期制作计划。",
        OBSERVATION_AFFIRMATIVE_PATTERNS,
    )
    _assert_no_affirmative_duties(
        "禁止同时输出 R 和 G。不得给出 formal grade。禁止提供迭代建议。"
        "不得制定后期制作计划。",
        REVIEW_AFFIRMATIVE_PATTERNS,
    )


def test_validators_reject_explicit_legacy_v2_mixed_appendix() -> None:
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_observation_prompt(
            _read_prompt("tiktok_video_observation.md") + LEGACY_V2_MIXED_APPENDIX
        )
    with pytest.raises(AssertionError, match="forbidden duties"):
        _validate_review_prompt(
            _read_prompt("tiktok_video_analysis.md") + LEGACY_V2_MIXED_APPENDIX
        )


@pytest.mark.parametrize(
    "schema",
    [
        '```json\n{"type": "object", "properties": {}}\n```',
        '```json\n[{"type": "object", "properties": {}}]\n```',
        '{"type": "object", "properties": {"score": {"type": "number"}}}',
        '{"type": "array", "items": {"type": "object"}}',
        '{"awarded_points": null, "confidence": null}',
        '[{"awarded_points": null, "confidence": null}]',
    ],
)
def test_schema_guard_rejects_complete_object_and_array_schemas(schema: str) -> None:
    with pytest.raises(AssertionError):
        _assert_no_schema_or_numeric_anchor(schema)


@pytest.mark.parametrize(
    "anchor",
    [
        "awarded_points=8",
        "confidence = 0.8",
        "score: 9",
        '"awarded_points": 8',
        '"confidence": 0.75',
        "awarded_points 为 8，confidence 为 0.8",
        "score 的值为 9",
        "confidence is 0.7",
        "awarded_points equals 6",
        "confidence of 0.6",
        "score to 7",
        "评分为 8 分",
        "置信度: 0.9",
    ],
)
def test_numeric_anchor_guard_rejects_scoring_and_confidence_examples(anchor: str) -> None:
    with pytest.raises(AssertionError):
        _assert_no_schema_or_numeric_anchor(anchor)


def test_numeric_anchor_guard_allows_timing_dimension_caps_and_g0_numbers() -> None:
    _assert_no_schema_or_numeric_anchor(
        "Timeline 使用 0.5 秒与 0.25 秒；C1 | 受众与购买需求 | 上限 6；"
        "G0 硬失败；仅引用 awarded_points、confidence、score 字段。"
    )


@pytest.mark.parametrize("missing", sorted(EXPECTED_G0_FAILURES))
def test_review_contract_rejects_each_missing_g0_failure(missing: str) -> None:
    prompt = _read_prompt("tiktok_video_analysis.md").replace(f"- [G0] {missing}\n", "")
    with pytest.raises(AssertionError):
        _validate_review_prompt(prompt)


@pytest.mark.parametrize("dimension", sorted(EXPECTED_DIMENSIONS))
def test_review_contract_rejects_each_missing_or_changed_dimension(
    dimension: tuple[str, str, int],
) -> None:
    dimension_id, name, max_points = dimension
    prompt = _read_prompt("tiktok_video_analysis.md").replace(
        f"- [{dimension_id[0]}] {dimension_id} | {name} | 上限 {max_points}\n",
        f"- [{dimension_id[0]}] {dimension_id} | 错误名称 | 上限 {max_points + 1}\n",
    )
    with pytest.raises(AssertionError):
        _validate_review_prompt(prompt)
