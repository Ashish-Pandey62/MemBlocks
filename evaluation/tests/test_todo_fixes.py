"""Unit tests for the TODO fixes in datasets/locomo.py and runners/locomo.py.

No infrastructure required — no Qdrant, MongoDB, or LLM API calls.

Run:
    cd /path/to/MemBlocks
    python -m pytest evaluation/tests/test_todo_fixes.py -v
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ---------------------------------------------------------------------------
# 1. _parse_locomo_datetime
# ---------------------------------------------------------------------------

from evaluation.datasets.locomo import _parse_locomo_datetime, LocomoMessage


class TestParseLocomoDatetime:
    def test_pm_time(self):
        result = _parse_locomo_datetime("1:56 pm on 8 May, 2023")
        assert result == datetime(2023, 5, 8, 13, 56)

    def test_am_time(self):
        result = _parse_locomo_datetime("10:37 am on 27 June, 2023")
        assert result == datetime(2023, 6, 27, 10, 37)

    def test_midnight_12am(self):
        # 12:xx am is midnight (00:xx)
        result = _parse_locomo_datetime("12:09 am on 13 September, 2023")
        assert result == datetime(2023, 9, 13, 0, 9)

    def test_year_boundary(self):
        result = _parse_locomo_datetime("12:19 am on 4 January, 2024")
        assert result == datetime(2024, 1, 4, 0, 19)

    def test_none_input(self):
        assert _parse_locomo_datetime(None) is None

    def test_empty_string(self):
        assert _parse_locomo_datetime("") is None

    def test_unparseable_returns_none(self):
        assert _parse_locomo_datetime("not a date at all") is None


# ---------------------------------------------------------------------------
# 2. Dataset loader populates date_time on messages
# ---------------------------------------------------------------------------

from evaluation.datasets.locomo import LocomoDataset
from evaluation.core.config import DatasetConfig


class TestDatasetDatetimePopulation:
    @pytest.fixture(scope="class")
    def sessions(self):
        config = DatasetConfig(name="locomo", max_sessions=2, max_questions_per_session=1)
        dataset = LocomoDataset(config)
        return dataset.load()

    def test_messages_have_datetime(self, sessions):
        for session in sessions:
            for msg in session.messages:
                assert msg.date_time is not None, (
                    f"session {session.session_id}: message role={msg.role!r} has no date_time"
                )

    def test_datetime_is_datetime_instance(self, sessions):
        for session in sessions:
            for msg in session.messages:
                assert isinstance(msg.date_time, datetime)

    def test_messages_have_distinct_datetimes_across_session_blocks(self, sessions):
        # A LocomoSession spans multiple session_X blocks (different conversation dates),
        # so there should be more than one unique datetime — one per session_X block.
        for session in sessions:
            datetimes = {msg.date_time for msg in session.messages}
            assert len(datetimes) > 1, (
                f"session {session.session_id}: expected multiple datetimes (one per session block), "
                f"got only {datetimes}"
            )


# ---------------------------------------------------------------------------
# 3. _pair_messages captures date_time from the user message (pre-increment fix)
# ---------------------------------------------------------------------------

from evaluation.runners.locomo import LocomoRunner
from evaluation.datasets.locomo import LocomoDataset, LocomoSession, LocomoQuestion
from evaluation.core.config import RunnerConfig


def _make_runner():
    config = RunnerConfig(name="locomo", model="dummy", judge_model="dummy")
    dataset = LocomoDataset(DatasetConfig(name="locomo", max_sessions=1))
    return LocomoRunner(config, dataset)


class TestPairMessages:
    def test_datetime_taken_from_user_message(self):
        dt_user = datetime(2023, 5, 8, 13, 56)
        dt_assistant = datetime(2023, 6, 1, 10, 0)
        messages = [
            LocomoMessage(role="user", content="hello", date_time=dt_user),
            LocomoMessage(role="assistant", content="hi", date_time=dt_assistant),
        ]
        runner = _make_runner()
        turns = runner._pair_messages(messages)
        assert len(turns) == 1
        user_msg, ai_resp, turn_dt = turns[0]
        assert turn_dt == dt_user, "date_time should come from the user message, not the next message"

    def test_solo_user_message_no_index_error(self):
        dt = datetime(2023, 5, 8, 13, 56)
        messages = [LocomoMessage(role="user", content="last msg", date_time=dt)]
        runner = _make_runner()
        turns = runner._pair_messages(messages)
        assert len(turns) == 1
        _, _, turn_dt = turns[0]
        assert turn_dt == dt

    def test_multiple_pairs_each_gets_user_datetime(self):
        dt1 = datetime(2023, 5, 8, 13, 56)
        dt2 = datetime(2023, 6, 1, 10, 0)
        messages = [
            LocomoMessage(role="user", content="q1", date_time=dt1),
            LocomoMessage(role="assistant", content="a1", date_time=dt1),
            LocomoMessage(role="user", content="q2", date_time=dt2),
            LocomoMessage(role="assistant", content="a2", date_time=dt2),
        ]
        runner = _make_runner()
        turns = runner._pair_messages(messages)
        assert len(turns) == 2
        assert turns[0][2] == dt1
        assert turns[1][2] == dt2


# ---------------------------------------------------------------------------
# 4. _freeze_datetime patches service modules correctly
# ---------------------------------------------------------------------------

from evaluation.runners.locomo import _freeze_datetime


class TestFreezeDatetime:
    def test_utcnow_returns_frozen_time(self):
        import memblocks.services.session as svc_session

        frozen = datetime(2023, 5, 8, 13, 56)
        with _freeze_datetime(frozen):
            result = svc_session.datetime.utcnow()
        assert result == frozen

    def test_now_returns_aware_frozen_time(self):
        import memblocks.services.semantic_memory as svc_sem

        frozen = datetime(2023, 5, 8, 13, 56)
        with _freeze_datetime(frozen):
            result = svc_sem.datetime.now(timezone.utc)
        assert result == frozen.replace(tzinfo=timezone.utc)

    def test_pipeline_utcnow_patched(self):
        import memblocks.services.memory_pipeline as svc_pipe

        frozen = datetime(2023, 9, 13, 0, 9)
        with _freeze_datetime(frozen):
            result = svc_pipe.datetime.utcnow()
        assert result == frozen

    def test_patch_is_removed_after_context(self):
        import memblocks.services.session as svc_session

        frozen = datetime(2023, 5, 8, 13, 56)
        with _freeze_datetime(frozen):
            pass
        # After the context, utcnow() should return real current time (not frozen)
        real_now = svc_session.datetime.utcnow()
        assert real_now != frozen

    def test_aware_input_preserved(self):
        import memblocks.services.session as svc_session

        frozen_aware = datetime(2023, 5, 8, 13, 56, tzinfo=timezone.utc)
        with _freeze_datetime(frozen_aware):
            result = svc_session.datetime.utcnow()
        # utcnow should return naive version
        assert result.tzinfo is None
        assert result == frozen_aware.replace(tzinfo=None)
