"""
Tests for S4-07, S4-08, S4-09, S4-10.

S4-07: stt.py magic bytes validation
S4-08: uv.lock / pyproject.toml dependency sync
S4-09: ChunkUsageLog soft delete
S4-10: Anti-cheat words_per_second combo
"""

import os
import time
import uuid
import pytest
from unittest.mock import MagicMock


# ═══════════════════════════════════════════════════════════════════════════════
# S4-07: Audio magic bytes validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestS407AudioMagicBytes:
    """_validate_audio rejects non-audio files via magic byte check."""

    def _validate(self, data: bytes):
        from app.services.stt import _validate_audio
        _validate_audio(data)

    def test_wav_accepted(self):
        """Valid WAV header passes validation."""
        wav = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 500
        self._validate(wav)  # Should not raise

    def test_ogg_accepted(self):
        """Valid OGG header passes."""
        ogg = b"OggS" + b"\x00" * 500
        self._validate(ogg)

    def test_webm_accepted(self):
        """Valid WebM EBML header passes."""
        webm = b"\x1a\x45\xdf\xa3" + b"\x00" * 500
        self._validate(webm)

    def test_mp3_id3_accepted(self):
        """Valid MP3 with ID3 tag passes."""
        mp3 = b"ID3" + b"\x00" * 500
        self._validate(mp3)

    def test_mp3_sync_accepted(self):
        """Valid MP3 frame sync passes."""
        mp3 = bytes([0xFF, 0xFB]) + b"\x00" * 500
        self._validate(mp3)

    def test_flac_accepted(self):
        """Valid FLAC header passes."""
        flac = b"fLaC" + b"\x00" * 500
        self._validate(flac)

    def test_random_bytes_rejected(self):
        """Non-audio bytes are rejected with STTError."""
        from app.services.stt import STTError
        garbage = b"\xDE\xAD\xBE\xEF" + b"\x00" * 500
        with pytest.raises(STTError, match="Invalid audio format"):
            self._validate(garbage)

    def test_pdf_rejected(self):
        """PDF file rejected."""
        from app.services.stt import STTError
        pdf = b"%PDF-1.4" + b"\x00" * 500
        with pytest.raises(STTError, match="Invalid audio format"):
            self._validate(pdf)

    def test_json_rejected(self):
        """JSON payload rejected."""
        from app.services.stt import STTError
        json_bytes = b'{"hello": "world"}' + b"\x00" * 500
        with pytest.raises(STTError, match="Invalid audio format"):
            self._validate(json_bytes)

    def test_too_short_rejected(self):
        """Audio shorter than minimum size rejected."""
        from app.services.stt import STTError
        with pytest.raises(STTError, match="Audio too short"):
            self._validate(b"RIFF" + b"\x00" * 10)

    def test_valid_magic_bytes_list(self):
        """All documented formats are in the valid list."""
        from app.services.stt import _VALID_MAGIC_BYTES
        formats = [fmt for _, _, fmt in _VALID_MAGIC_BYTES]
        assert "WAV" in formats
        assert "OGG/Opus" in formats
        assert "WebM" in formats
        assert "MP3" in formats
        assert "FLAC" in formats


# ═══════════════════════════════════════════════════════════════════════════════
# S4-08: Dependency sync — python-jose removed
# ═══════════════════════════════════════════════════════════════════════════════

class TestS408DependencySync:
    """python-jose removed from uv.lock; PyJWT is the active JWT library."""

    def test_pyjwt_is_used(self):
        """The codebase imports jwt (PyJWT), not jose."""
        import jwt
        assert hasattr(jwt, "encode")
        assert hasattr(jwt, "decode")

    def test_pyproject_has_pyjwt(self):
        """pyproject.toml lists PyJWT, not python-jose."""
        pyproject_path = os.path.join(
            os.path.dirname(__file__), "..", "pyproject.toml"
        )
        with open(pyproject_path) as f:
            content = f.read()
        assert "PyJWT" in content
        # python-jose may appear in a comment, but not as a dependency line
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                continue
            assert "python-jose" not in line or "migrated" in line.lower()

    def test_uv_lock_no_python_jose(self):
        """uv.lock should not contain python-jose as a dependency."""
        lock_path = os.path.join(
            os.path.dirname(__file__), "..", "uv.lock"
        )
        with open(lock_path) as f:
            content = f.read()
        # Should not have python-jose as a package name
        assert 'name = "python-jose"' not in content

    def test_security_uses_jwt_not_jose(self):
        """security.py imports jwt, not jose."""
        from app.core import security
        import inspect
        source = inspect.getsource(security)
        assert "import jwt" in source
        assert "from jose" not in source
        assert "import jose" not in source


# ═══════════════════════════════════════════════════════════════════════════════
# S4-09: ChunkUsageLog soft delete
# ═══════════════════════════════════════════════════════════════════════════════

class TestS409SoftDelete:
    """ChunkUsageLog has is_deleted flag and archived_at timestamp."""

    def test_model_has_is_deleted(self):
        """ChunkUsageLog model has is_deleted column."""
        from app.models.rag import ChunkUsageLog
        assert hasattr(ChunkUsageLog, "is_deleted")

    def test_model_has_archived_at(self):
        """ChunkUsageLog model has archived_at column."""
        from app.models.rag import ChunkUsageLog
        assert hasattr(ChunkUsageLog, "archived_at")

    def test_is_deleted_defaults_false(self):
        """is_deleted defaults to False."""
        from app.models.rag import ChunkUsageLog
        col = ChunkUsageLog.__table__.columns["is_deleted"]
        # Check Python-side default
        assert col.default.arg is False

    def test_is_deleted_is_indexed(self):
        """is_deleted column is indexed for query performance."""
        from app.models.rag import ChunkUsageLog
        col = ChunkUsageLog.__table__.columns["is_deleted"]
        assert col.index is True


# ═══════════════════════════════════════════════════════════════════════════════
# S4-10: Anti-cheat words_per_second
# ═══════════════════════════════════════════════════════════════════════════════

class TestS410WpsRealtime:
    """Real-time anti-cheat checks words-per-second."""

    def test_wps_constants_exist(self):
        from app.services.anti_cheat_realtime import SUSPICIOUS_WPS, WPS_MIN_WORDS
        assert SUSPICIOUS_WPS == 15.0
        assert WPS_MIN_WORDS == 10

    def test_normal_typing_no_flag(self):
        """Normal typing speed (5 wps) should not trigger."""
        from app.services.anti_cheat_realtime import init_player, check_message

        uid = uuid.uuid4()
        did = uuid.uuid4()
        init_player(uid, did)

        # First message to establish timing
        check_message(uid, did, "hello", timestamp=100.0)

        # 20 words in 5 seconds = 4 wps → OK
        text = " ".join(["word"] * 20)
        result = check_message(uid, did, text, timestamp=105.0)
        wps_flags = [f for f in result.flags if "high_wps" in f]
        assert len(wps_flags) == 0

    def test_superhuman_wps_flagged(self):
        """60 words in 3.5 seconds = 17 wps → flagged."""
        from app.services.anti_cheat_realtime import init_player, check_message, cleanup_duel

        uid = uuid.uuid4()
        did = uuid.uuid4()
        init_player(uid, did)

        check_message(uid, did, "start", timestamp=200.0)

        # 60 words in 3.5s = 17.1 wps → above 15 threshold
        text = " ".join(["word"] * 60)
        result = check_message(uid, did, text, timestamp=203.5)
        wps_flags = [f for f in result.flags if "high_wps" in f]
        assert len(wps_flags) == 1
        assert "17.1" in wps_flags[0]

        cleanup_duel(did)

    def test_sleep_bypass_caught(self):
        """sleep(3.1) with 50 words = 16.1 wps → caught by S4-10."""
        from app.services.anti_cheat_realtime import init_player, check_message, cleanup_duel

        uid = uuid.uuid4()
        did = uuid.uuid4()
        init_player(uid, did)

        check_message(uid, did, "prompt", timestamp=300.0)

        # 50 words in 3.1s = 16.1 wps → above threshold
        # This would bypass the old 3s check (elapsed > 3.0)
        text = " ".join(["word"] * 50)
        result = check_message(uid, did, text, timestamp=303.1)

        # Old check: 50 words but 3.1s > 3.0 → NOT flagged by fast_long
        fast_flags = [f for f in result.flags if "fast_long" in f]
        assert len(fast_flags) == 0  # Not triggered (> 3.0s)

        # New check: 50/3.1 = 16.1 wps → flagged by high_wps
        wps_flags = [f for f in result.flags if "high_wps" in f]
        assert len(wps_flags) == 1

        cleanup_duel(did)

    def test_short_message_not_checked(self):
        """Messages with < WPS_MIN_WORDS are not checked for wps."""
        from app.services.anti_cheat_realtime import init_player, check_message, cleanup_duel

        uid = uuid.uuid4()
        did = uuid.uuid4()
        init_player(uid, did)

        check_message(uid, did, "go", timestamp=400.0)

        # 5 words in 0.2s = 25 wps, but too few words → skip
        text = " ".join(["ok"] * 5)
        result = check_message(uid, did, text, timestamp=400.2)
        wps_flags = [f for f in result.flags if "high_wps" in f]
        assert len(wps_flags) == 0

        cleanup_duel(did)


class TestS410WpsPostMatch:
    """Post-match anti-cheat also detects high wps patterns."""

    def test_post_match_wps_in_behavioral(self):
        """check_behavioral detects high wps across multiple messages."""
        from app.services.anti_cheat import check_behavioral

        uid = uuid.uuid4()
        uid_str = str(uid)

        # Simulate messages with latencies and word counts
        messages = [
            {"sender_id": uid_str, "text": " ".join(["word"] * 40),
             "latency_ms": 2500, "timestamp": 100},  # 40w/2.5s = 16 wps
            {"sender_id": "other", "text": "reply", "timestamp": 101},
            {"sender_id": uid_str, "text": " ".join(["term"] * 30),
             "latency_ms": 1800, "timestamp": 105},  # 30w/1.8s = 16.7 wps
            {"sender_id": "other", "text": "reply2", "timestamp": 106},
            {"sender_id": uid_str, "text": " ".join(["data"] * 20),
             "latency_ms": 5000, "timestamp": 112},  # 20w/5s = 4 wps → OK
        ]

        result = check_behavioral(
            messages=messages,
            user_id=uid,
        )

        # Should detect high_wps_responses in details.flags
        flags = result.details.get("flags", [])
        assert any("high_wps" in f for f in flags)
