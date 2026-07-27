from voice_suite.briefing import BriefingComposer, BriefingItem
from voice_suite.meeting import MeetingMode, MeetingOrchestrator, MeetingPolicy


def test_briefing_prioritizes_high_items_and_adds_one_step():
    text = BriefingComposer().compose(
        today=[BriefingItem("保険更新", "夜に実施", "high")],
        proactive_suggestion="15分だけ準備する。",
    )
    assert "最優先。保険更新。夜に実施" in text
    assert "今日の一手です。" in text


def test_briefing_does_not_invent_empty_sections():
    text = BriefingComposer().compose(today=[])
    assert "今日の重要事項" not in text
    assert "直近の注意事項" not in text


def test_driving_mode_does_not_echo_and_keeps_replies_short():
    meeting = MeetingOrchestrator(MeetingPolicy(mode=MeetingMode.DRIVING))
    assert meeting.user_turn("  今日は   どうする？ ") == "今日は どうする？"
    reply = meeting.prepare_reply("あ" * 600)
    assert reply.endswith("詳しい内容は運転終了後に確認できます。")
    assert len(reply) <= 420


def test_actions_require_explicit_confirmation():
    meeting = MeetingOrchestrator()
    reply = meeting.prepare_reply("カレンダーに予定を追加できます。", action="calendar.create")
    assert "明示的に『実行して』" in reply


def test_meeting_close_has_no_echo_when_empty():
    assert "決定事項はありません" in MeetingOrchestrator().meeting_close()
