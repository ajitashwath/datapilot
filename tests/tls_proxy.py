import datetime
import ipaddress
import socket
import ssl
import struct
import threading
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

SSL_REQUEST_CODE = 80877103


def make_certificate(directory: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1")])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = directory / "proxy.crt", directory / "proxy.key"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return cert_path, key_path


def pipe(source: socket.socket, target: socket.socket) -> None:
    try:
        while data := source.recv(65536):
            target.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (source, target):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class TlsPostgresProxy:
    def __init__(self, upstream_host: str, upstream_port: int, directory: Path):
        self.upstream = (upstream_host, upstream_port)
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cert, key = make_certificate(directory)
        self.context.load_cert_chain(cert, key)
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.port = self.listener.getsockname()[1]
        self.tls_sessions = 0
        self.plain_sessions = 0
        self.thread = threading.Thread(target=self.serve, daemon=True)

    def start(self) -> "TlsPostgresProxy":
        self.thread.start()
        return self

    def stop(self) -> None:
        self.listener.close()

    def serve(self) -> None:
        while True:
            try:
                client, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(client,), daemon=True).start()

    def handle(self, client: socket.socket) -> None:
        try:
            first = client.recv(8, socket.MSG_PEEK)
            upstream = socket.create_connection(self.upstream)
            if len(first) == 8 and struct.unpack("!II", first) == (8, SSL_REQUEST_CODE):
                client.recv(8)
                client.sendall(b"S")
                client = self.context.wrap_socket(client, server_side=True)
                self.tls_sessions += 1
            else:
                self.plain_sessions += 1
            threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
            pipe(upstream, client)
        except (OSError, ssl.SSLError):
            client.close()
