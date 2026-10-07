import email
import socketserver
import threading
import time
from email.message import Message


class SmtpHandler(socketserver.StreamRequestHandler):
    def reply(self, line: str) -> None:
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self) -> None:
        self.reply("220 sink ready")
        sender, recipients = "", []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            command = line.decode(errors="replace").strip()
            upper = command.upper()
            if upper.startswith(("EHLO", "HELO")):
                self.reply("250 sink")
            elif upper.startswith("MAIL FROM"):
                sender, recipients = command[10:].strip(), []
                self.reply("250 ok")
            elif upper.startswith("RCPT TO"):
                recipients.append(command[8:].strip().strip("<>"))
                self.reply("250 ok")
            elif upper == "DATA":
                self.reply("354 go ahead")
                chunks = []
                while True:
                    data_line = self.rfile.readline()
                    if data_line in (b".\r\n", b""):
                        break
                    chunks.append(data_line[1:] if data_line.startswith(b"..") else data_line)
                self.server.sink.deliver(sender, recipients, email.message_from_bytes(b"".join(chunks)))
                self.reply("250 queued")
            elif upper == "QUIT":
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


class SmtpSink:
    def __init__(self):
        self.messages: list[tuple[str, list[str], Message]] = []
        self.guard = threading.Lock()
        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), SmtpHandler)
        self.server.daemon_threads = True
        self.server.sink = self
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> "SmtpSink":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def deliver(self, sender: str, recipients: list[str], message: Message) -> None:
        with self.guard:
            self.messages.append((sender, recipients, message))

    def wait_for(self, count: int, timeout: float = 5.0) -> list[Message]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.guard:
                if len(self.messages) >= count:
                    return [m for _, _, m in self.messages]
            time.sleep(0.02)
        with self.guard:
            return [m for _, _, m in self.messages]

    def settle(self, seconds: float = 0.4) -> int:
        time.sleep(seconds)
        with self.guard:
            return len(self.messages)

    @staticmethod
    def body(message: Message) -> str:
        return message.get_payload(decode=True).decode()
