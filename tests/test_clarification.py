from voice_suite.meeting import MeetingOrchestrator


def test_clarification_reply_is_short_and_actionable():
    reply = MeetingOrchestrator().clarification_reply()
    assert reply == "すみません、うまく聞き取れませんでした。もう一度お願いします。"
