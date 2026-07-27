from voice_suite.context_guard import ActionRisk, ContextFact, ContextGuard


def test_low_risk_action_does_not_need_step_up():
    guard = ContextGuard()
    assert guard.begin(action="calendar.read", risk=ActionRisk.NONE) is None


def test_high_risk_action_uses_trusted_context_fact_and_keyword():
    guard = ContextGuard()
    challenge = guard.begin(
        action="calendar.update",
        risk=ActionRisk.HIGH,
        fact=ContextFact(
            question="今週土曜に行くのは何県ですか？",
            answer="神奈川県",
            alternatives=("神奈川",),
        ),
    )
    assert challenge is not None
    assert challenge.question == "今週土曜に行くのは何県ですか？"
    assert not guard.answer("はい")
    assert guard.pending is None

    challenge = guard.begin(
        action="calendar.update",
        risk=ActionRisk.HIGH,
        fact=ContextFact("今週土曜に行くのは何県ですか？", "神奈川県"),
    )
    assert challenge is not None
    assert guard.answer("神奈川県です")
    assert not guard.authorize_action("はい")
    assert guard.authorize_action("実行して")
    assert guard.pending is None


def test_anomaly_without_trusted_fact_fails_closed():
    guard = ContextGuard()
    challenge = guard.begin(
        action="external.send",
        risk=ActionRisk.REVERSIBLE,
        anomalous=True,
    )
    assert challenge is not None
    assert "実行しません" in challenge.question
    assert not guard.answer("分かりません")
    assert guard.metrics.rejected == 1


def test_stop_is_immediate_and_does_not_execute():
    guard = ContextGuard()
    guard.begin(
        action="calendar.delete",
        risk=ActionRisk.HIGH,
        fact=ContextFact("今週投稿する作家は誰ですか？", "ルイーズさん"),
    )
    assert guard.is_cancel("止めて")
    assert not guard.answer("止めて")
    assert guard.pending is None
    assert not guard.authorize_action("実行して")
    assert guard.metrics.cancelled == 1
