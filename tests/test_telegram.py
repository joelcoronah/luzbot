import threading

from luzbot.telegram import CommandListener, Notifier, TelegramError


class FakeClient:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.sent: list[tuple[str, str]] = []
        self.done = threading.Event()

    def send_message(self, chat_id: str, text: str) -> None:
        if self.failures:
            self.failures -= 1
            raise TelegramError("boom")
        self.sent.append((chat_id, text))
        self.done.set()


def test_notifier_retries_until_delivered():
    client = FakeClient(failures=2)
    notifier = Notifier(client, "42", initial_backoff=0.01)
    notifier.start()
    notifier("hello")
    assert client.done.wait(2)
    notifier.stop()
    assert client.sent == [("42", "hello")]


def make_update(chat_id, text):
    return {"update_id": 1, "message": {"chat": {"id": chat_id}, "text": text}}


def test_listener_only_answers_configured_chat():
    replies: list[str] = []
    listener = CommandListener(
        client=None, chat_id="42", handlers={"/estado": lambda: "ok"}, reply=replies.append
    )
    listener.handle_update(make_update(42, "/estado"))
    listener.handle_update(make_update(42, "/estado@luz_bot extra"))
    listener.handle_update(make_update(999, "/estado"))  # stranger
    listener.handle_update(make_update(42, "/unknown"))
    listener.handle_update(make_update(42, ""))
    listener.handle_update({"update_id": 2})
    assert replies == ["ok", "ok"]
