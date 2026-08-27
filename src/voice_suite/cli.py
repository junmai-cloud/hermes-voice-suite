"""Local demo CLI for the shared voice-agent core."""

import sys

from .briefing import BriefingComposer, BriefingItem
from .meeting import MeetingMode, MeetingOrchestrator, MeetingPolicy


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "tech":
        from .technical_cli import main as technical_main

        raise SystemExit(technical_main(sys.argv[2:]))
    composer = BriefingComposer()
    print(composer.compose(
        today=[BriefingItem("夜の保険更新", "20時30分から。", "high")],
        upcoming=[BriefingItem("7月29日の検査", "朝は食事を取らない注意があります。", "high")],
        trends=[BriefingItem("写真イベント", "投稿の参考になりそうな直近の話題を確認します。")],
        proactive_suggestion="今日は投稿後に、写真集の準備を15分だけ進めるのがおすすめです。",
    ))
    meeting = MeetingOrchestrator(MeetingPolicy(mode=MeetingMode.DRIVING))
    meeting.user_turn("今日の通常業務をどう進める？")
    print("\n--- meeting reply ---")
    print(meeting.prepare_reply("まず給与関係を確認し、その後に期限のある作業を片付けるのがおすすめです。"))


if __name__ == "__main__":
    main()
