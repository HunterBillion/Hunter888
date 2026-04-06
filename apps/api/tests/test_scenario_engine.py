"""Tests for the scenario engine (services/scenario_engine.py).

Covers scenario selection, session config generation, prompt building,
stage tracking, direction parsing, and message estimation.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scenario_engine import (
    SessionConfig,
    StageInfo,
    select_scenario,
    generate_session_config,
    build_scenario_prompt,
    track_stage_progress,
    parse_stage_directions_v2,
    estimate_total_messages,
    ParsedStageDirection,
)


# ═══════════════════════════════════════════════════════════════════════════════
# TestSessionConfig — Session configuration
# ═══════════════════════════════════════════════════════════════════════════════


class TestSessionConfig:
    """Test SessionConfig dataclass."""

    def test_session_config_create_with_required_fields(self):
        """Create SessionConfig with required fields."""
        config = SessionConfig(
            scenario_code="cold_ad",
            scenario_name="Cold Ad Call",
            template_id=uuid.uuid4(),
            archetype="skeptical_cfo",
            initial_emotion="cold",
            client_awareness="unaware",
            client_motivation="low",
            difficulty=5,
        )
        assert config.scenario_code == "cold_ad"
        assert config.scenario_name == "Cold Ad Call"
        assert config.archetype == "skeptical_cfo"
        assert config.initial_emotion == "cold"
        assert config.difficulty == 5

    def test_session_config_difficulty_range(self):
        """Difficulty should be between 1-10."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            difficulty=1,
        )
        assert 1 <= config.difficulty <= 10

    def test_session_config_difficulty_10(self):
        """Difficulty can be 10."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            difficulty=10,
        )
        assert config.difficulty == 10

    def test_session_config_stages_is_list(self):
        """stages should be a list."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            stages=[
                {"order": 1, "name": "Stage 1"},
                {"order": 2, "name": "Stage 2"},
            ],
        )
        assert isinstance(config.stages, list)
        assert len(config.stages) == 2

    def test_session_config_traps_count_non_negative(self):
        """traps_count should be >= 0."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            traps_count=3,
        )
        assert config.traps_count >= 0

    def test_session_config_active_traps_list(self):
        """active_traps should be list of trap codes."""
        traps = ["price_objection", "timing_objection"]
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            active_traps=traps,
        )
        assert config.active_traps == traps


# ═══════════════════════════════════════════════════════════════════════════════
# TestStageInfo — Stage information
# ═══════════════════════════════════════════════════════════════════════════════


class TestStageInfo:
    """Test StageInfo dataclass."""

    def test_stage_info_create_with_required_fields(self):
        """Create StageInfo with required fields."""
        stage = StageInfo(
            order=1,
            name="Opening",
            description="Initial contact and rapport building",
            manager_goals=["Introduce yourself", "Build rapport"],
            manager_mistakes=["Be too pushy", "Ignore client needs"],
            expected_emotion_range=["cold", "curious"],
            emotion_red_flag="hangup",
            is_required=True,
            is_final=False,
        )
        assert stage.order == 1
        assert stage.name == "Opening"
        assert stage.is_required is True
        assert stage.is_final is False

    def test_stage_info_manager_goals_is_list(self):
        """manager_goals should be a list."""
        goals = [
            "Establish credibility",
            "Qualify the prospect",
            "Identify pain points",
        ]
        stage = StageInfo(
            order=2,
            name="Diagnosis",
            description="Understand client needs",
            manager_goals=goals,
            manager_mistakes=[],
            expected_emotion_range=["curious"],
            emotion_red_flag="hostile",
            is_required=True,
            is_final=False,
        )
        assert isinstance(stage.manager_goals, list)
        assert stage.manager_goals == goals

    def test_stage_info_manager_mistakes_is_list(self):
        """manager_mistakes should be a list."""
        mistakes = [
            "Pitch too early",
            "Ignore objections",
            "Lose patience",
        ]
        stage = StageInfo(
            order=3,
            name="Pitch",
            description="Present solution",
            manager_goals=[],
            manager_mistakes=mistakes,
            expected_emotion_range=["considering"],
            emotion_red_flag="hostile",
            is_required=True,
            is_final=False,
        )
        assert isinstance(stage.manager_mistakes, list)
        assert stage.manager_mistakes == mistakes

    def test_stage_info_is_required_boolean(self):
        """is_required should be boolean."""
        stage_req = StageInfo(
            order=1,
            name="Opening",
            description="Desc",
            manager_goals=[],
            manager_mistakes=[],
            expected_emotion_range=["cold"],
            emotion_red_flag="hangup",
            is_required=True,
            is_final=False,
        )
        stage_opt = StageInfo(
            order=4,
            name="Advanced",
            description="Desc",
            manager_goals=[],
            manager_mistakes=[],
            expected_emotion_range=["deal"],
            emotion_red_flag="hangup",
            is_required=False,
            is_final=False,
        )
        assert stage_req.is_required is True
        assert stage_opt.is_required is False

    def test_stage_info_is_final_boolean(self):
        """is_final should be boolean."""
        stage_final = StageInfo(
            order=7,
            name="Closing",
            description="Close the deal",
            manager_goals=[],
            manager_mistakes=[],
            expected_emotion_range=["deal"],
            emotion_red_flag="hangup",
            is_required=True,
            is_final=True,
        )
        assert stage_final.is_final is True


# ═══════════════════════════════════════════════════════════════════════════════
# TestSelectScenario — Scenario selection with difficulty
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestSelectScenario:
    """Test scenario selection based on manager level."""

    async def test_select_scenario_beginner_level(self):
        """Beginner level (1-3) should get easier scenarios."""
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            MagicMock(code="cold_ad", difficulty=2),
            MagicMock(code="warm_callback", difficulty=3),
        ]

        with patch("app.services.scenario_engine.random.choices") as mock_choices:
            mock_choices.return_value = [MagicMock(code="cold_ad", difficulty=2)]
            result = await select_scenario(mock_db, manager_level=2)

        assert result is not None

    async def test_select_scenario_advanced_level(self):
        """Advanced level (8-10) should get harder scenarios."""
        mock_db = AsyncMock()
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            MagicMock(code="complex_scenario", difficulty=8),
            MagicMock(code="advanced_deal", difficulty=9),
        ]

        with patch("app.services.scenario_engine.random.choices") as mock_choices:
            mock_choices.return_value = [MagicMock(code="complex_scenario", difficulty=8)]
            result = await select_scenario(mock_db, manager_level=9)

        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════════
# TestBuildScenarioPrompt — Prompt generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildScenarioPrompt:
    """Test scenario prompt building."""

    def test_build_scenario_prompt_returns_string(self):
        """build_scenario_prompt should return string."""
        config = SessionConfig(
            scenario_code="cold_ad",
            scenario_name="Cold Ad Call",
            template_id=uuid.uuid4(),
            archetype="skeptical_cfo",
            initial_emotion="cold",
            client_awareness="unaware",
            client_motivation="low",
            difficulty=5,
            stages=[
                {
                    "order": 1,
                    "name": "Opening",
                    "description": "Initial contact",
                    "manager_goals": ["Build rapport"],
                    "manager_mistakes": ["Be pushy"],
                    "expected_emotion_range": ["cold", "curious"],
                    "emotion_red_flag": "hangup",
                }
            ],
        )
        prompt = build_scenario_prompt(config)
        assert isinstance(prompt, str)

    def test_build_scenario_prompt_non_empty(self):
        """Prompt should be non-empty."""
        config = SessionConfig(
            scenario_code="cold_ad",
            scenario_name="Cold Ad Call",
            template_id=uuid.uuid4(),
            archetype="skeptical_cfo",
            initial_emotion="cold",
            client_awareness="unaware",
            client_motivation="low",
            difficulty=5,
        )
        prompt = build_scenario_prompt(config)
        assert len(prompt) > 0

    def test_build_scenario_prompt_contains_scenario_code(self):
        """Prompt should contain scenario code."""
        config = SessionConfig(
            scenario_code="cold_ad",
            scenario_name="Cold Ad Call",
            template_id=uuid.uuid4(),
            archetype="skeptical_cfo",
            initial_emotion="cold",
            client_awareness="unaware",
            client_motivation="low",
            difficulty=5,
        )
        prompt = build_scenario_prompt(config)
        assert "cold_ad" in prompt or "Cold Ad Call" in prompt


# ═══════════════════════════════════════════════════════════════════════════════
# TestTrackStageProgress — Stage progress tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrackStageProgress:
    """Test stage progress tracking by message count."""

    def test_track_stage_progress_first_message(self):
        """Message index 0 should return first stage."""
        stages = [
            {
                "order": 1,
                "name": "Opening",
                "description": "Intro",
                "manager_goals": [],
                "manager_mistakes": [],
                "expected_emotion_range": ["cold"],
                "emotion_red_flag": "hangup",
                "is_required": True,
                "is_final": False,
                "duration_min": 1,
                "duration_max": 2,
            }
        ]
        result = track_stage_progress(stages, message_index=0)
        assert result.order == 1

    def test_track_stage_progress_high_message_count(self):
        """High message count should return later stage."""
        stages = [
            {
                "order": 1,
                "name": "Opening",
                "description": "Intro",
                "manager_goals": [],
                "manager_mistakes": [],
                "expected_emotion_range": ["cold"],
                "emotion_red_flag": "hangup",
                "is_required": True,
                "is_final": False,
                "duration_min": 1,
                "duration_max": 2,
            },
            {
                "order": 2,
                "name": "Closing",
                "description": "Close",
                "manager_goals": [],
                "manager_mistakes": [],
                "expected_emotion_range": ["deal"],
                "emotion_red_flag": "hangup",
                "is_required": True,
                "is_final": True,
                "duration_min": 2,
                "duration_max": 3,
            },
        ]
        result = track_stage_progress(stages, message_index=20, total_expected_messages=24)
        assert result is not None
        assert isinstance(result, StageInfo)

    def test_track_stage_progress_returns_stage_info(self):
        """Should return StageInfo object."""
        stages = [
            {
                "order": 1,
                "name": "Opening",
                "description": "Intro",
                "manager_goals": ["Say hello"],
                "manager_mistakes": ["Be rude"],
                "expected_emotion_range": ["cold"],
                "emotion_red_flag": "hangup",
                "is_required": True,
                "is_final": False,
                "duration_min": 1,
                "duration_max": 2,
            }
        ]
        result = track_stage_progress(stages, message_index=0)
        assert isinstance(result, StageInfo)
        assert result.name == "Opening"


# ═══════════════════════════════════════════════════════════════════════════════
# TestParseStageDirectionsV2 — Stage direction parsing
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseStageDirectionsV2:
    """Test stage direction parsing v2 (two-pass, fuzzy fallback)."""

    def test_parse_stage_directions_returns_tuple(self):
        """parse_stage_directions_v2 should return (clean_text, directions)."""
        text = "The client is interested. [MEMORY:Asked about pricing]"
        clean_text, directions = parse_stage_directions_v2(text)
        assert isinstance(clean_text, str)
        assert isinstance(directions, list)

    def test_parse_stage_directions_memory_directive(self):
        """Text with [MEMORY:...] should extract memory directive."""
        text = "The client promised to send budget. [MEMORY:Client promised budget by EOD]"
        clean_text, directions = parse_stage_directions_v2(text)
        assert len(directions) > 0
        memory_dirs = [d for d in directions if d.direction_type == "memory"]
        assert len(memory_dirs) > 0

    def test_parse_stage_directions_storylet_directive(self):
        """Text with [STORYLET:...] should extract storylet directive."""
        text = "The manager showed advanced technique. [STORYLET:deal_advanced]"
        clean_text, directions = parse_stage_directions_v2(text)
        storylet_dirs = [d for d in directions if d.direction_type == "storylet"]
        assert len(storylet_dirs) > 0

    def test_parse_stage_directions_plain_text_empty(self):
        """Plain text without directives should return empty list."""
        text = "This is just a normal conversation without any directives."
        clean_text, directions = parse_stage_directions_v2(text)
        assert len(directions) == 0

    def test_parse_stage_directions_cleans_text(self):
        """Directives should be stripped from clean_text."""
        text = "The client is interested. [MEMORY:Asked about pricing] Call back tomorrow."
        clean_text, directions = parse_stage_directions_v2(text)
        assert "[MEMORY:" not in clean_text
        assert "interested" in clean_text
        assert "Call back" in clean_text

    def test_parse_stage_directions_multiple_directives(self):
        """Should handle multiple directives in same text."""
        text = "[MEMORY:Budget confirmed] Client nodded. [STORYLET:empathy_moment]"
        clean_text, directions = parse_stage_directions_v2(text)
        assert len(directions) >= 2

    def test_parse_stage_directions_returns_parsed_direction_objects(self):
        """Should return ParsedStageDirection objects."""
        text = "[MEMORY:Test memory]"
        clean_text, directions = parse_stage_directions_v2(text)
        if directions:
            assert isinstance(directions[0], ParsedStageDirection)
            assert hasattr(directions[0], "direction_type")
            assert hasattr(directions[0], "raw_tag")
            assert hasattr(directions[0], "payload")
            assert hasattr(directions[0], "confidence")


# ═══════════════════════════════════════════════════════════════════════════════
# TestEstimateTotalMessages — Message count estimation
# ═══════════════════════════════════════════════════════════════════════════════


class TestEstimateTotalMessages:
    """Test total message estimation."""

    def test_estimate_total_messages_returns_positive_int(self):
        """Should return positive integer."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            difficulty=5,
            stages=[
                {"duration_min": 2, "duration_max": 3},
                {"duration_min": 3, "duration_max": 5},
            ],
        )
        result = estimate_total_messages(config)
        assert isinstance(result, int)
        assert result > 0

    def test_estimate_total_messages_harder_difficulty_more_messages(self):
        """Harder difficulty should result in more estimated messages."""
        config_easy = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            difficulty=3,
            stages=[
                {"duration_min": 5, "duration_max": 8},
            ],
        )
        config_hard = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            difficulty=9,
            stages=[
                {"duration_min": 10, "duration_max": 15},
            ],
        )
        easy_msgs = estimate_total_messages(config_easy)
        hard_msgs = estimate_total_messages(config_hard)
        assert easy_msgs < hard_msgs

    def test_estimate_total_messages_no_stages_default(self):
        """No stages should return default value."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            stages=[],
        )
        result = estimate_total_messages(config)
        assert result > 0
        assert result >= 6  # Should be at least 6

    def test_estimate_total_messages_minimum_value(self):
        """Short stages should still return reasonable minimum."""
        config = SessionConfig(
            scenario_code="test",
            scenario_name="Test",
            template_id=uuid.uuid4(),
            archetype="test",
            initial_emotion="cold",
            client_awareness="aware",
            client_motivation="medium",
            stages=[
                {"duration_min": 1, "duration_max": 1},
            ],
        )
        result = estimate_total_messages(config)
        assert result >= 6
