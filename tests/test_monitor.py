from luzbot.monitor import Status


def test_first_heartbeat_announces_monitoring(make_monitor, sent):
    monitor = make_monitor()
    assert monitor.status is Status.UNKNOWN

    monitor.heartbeat()

    assert monitor.status is Status.ONLINE
    assert len(sent) == 1
    assert "Monitoring active" in sent[0]


def test_no_alert_while_heartbeats_keep_coming(make_monitor, sent, clock):
    monitor = make_monitor(timeout=180)
    monitor.heartbeat()
    for _ in range(10):
        clock.advance(60)
        monitor.heartbeat()
        monitor.check()
    assert monitor.status is Status.ONLINE
    assert len(sent) == 1  # only the "monitoring active" message


def test_outage_detected_after_timeout(make_monitor, sent, clock):
    monitor = make_monitor(timeout=180)
    monitor.heartbeat()

    clock.advance(180)
    monitor.check()
    assert monitor.status is Status.ONLINE  # exactly at the limit: still fine

    clock.advance(1)
    monitor.check()
    assert monitor.status is Status.OFFLINE
    assert "No signal from home" in sent[-1]
    assert "23/11 12:00" in sent[-1]  # last heartbeat, in Caracas time


def test_outage_alert_is_sent_once(make_monitor, sent, clock):
    monitor = make_monitor(timeout=180)
    monitor.heartbeat()
    clock.advance(200)
    monitor.check()
    clock.advance(600)
    monitor.check()
    monitor.check()
    assert sum("No signal" in m for m in sent) == 1


def test_recovery_reports_duration(make_monitor, sent, clock, storage):
    monitor = make_monitor(timeout=180)
    monitor.heartbeat()
    clock.advance(200)
    monitor.check()

    clock.advance(78 * 60 - 200)  # back 78 minutes after the last heartbeat
    monitor.heartbeat()

    assert monitor.status is Status.ONLINE
    assert "Home is back online" in sent[-1]
    assert "1 h 18 min" in sent[-1]
    [outage] = storage.recent_outages()
    assert outage.ended_at is not None
    assert outage.duration(clock()) == 78 * 60


def test_restart_grace_period(storage, sent, messages, clock):
    from luzbot.monitor import Monitor

    first = Monitor(storage, sent.append, messages, 180, clock=clock)
    first.heartbeat()

    # The server itself was down for an hour; home kept sending heartbeats
    # that never arrived. A fresh process must not alert immediately.
    clock.advance(3600)
    restarted = Monitor(storage, sent.append, messages, 180, clock=clock)
    restarted.check()
    assert restarted.status is Status.ONLINE

    clock.advance(60)
    restarted.heartbeat()
    clock.advance(60)
    restarted.check()
    assert restarted.status is Status.ONLINE
    assert not any("No signal" in m for m in sent)


def test_restart_during_outage_keeps_state(storage, sent, messages, clock):
    from luzbot.monitor import Monitor

    first = Monitor(storage, sent.append, messages, 180, clock=clock)
    first.heartbeat()
    clock.advance(300)
    first.check()
    assert first.status is Status.OFFLINE

    restarted = Monitor(storage, sent.append, messages, 180, clock=clock)
    assert restarted.status is Status.OFFLINE
    clock.advance(600)
    restarted.heartbeat()
    assert "Home is back online" in sent[-1]
    assert sum("No signal" in m for m in sent) == 1


def test_charging_warnings(make_monitor, sent):
    monitor = make_monitor()
    monitor.heartbeat(charging=True)
    monitor.heartbeat(charging=False)
    monitor.heartbeat(charging=False)
    monitor.heartbeat(charging=None)
    monitor.heartbeat(charging=True)

    assert sum("not charging" in m for m in sent) == 1
    assert "charging again" in sent[-1]


def test_status_and_history_reports(make_monitor, clock):
    monitor = make_monitor(timeout=180)
    assert "No heartbeat received" in monitor.status_report()
    assert "No outages" in monitor.history_report()

    monitor.heartbeat()
    clock.advance(30)
    assert "Home is online" in monitor.status_report()
    assert "0 outage(s)" in monitor.status_report()

    clock.advance(400)
    monitor.check()
    report = monitor.status_report()
    assert "No signal from home since" in report
    assert "1 outage(s)" in report
    assert "ongoing" in monitor.history_report()

    clock.advance(3000)
    monitor.heartbeat()
    history = monitor.history_report()
    assert "ongoing" not in history
    assert history.count("•") == 1
