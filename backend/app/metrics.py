import threading


class Metrics:
    def __init__(self):
        self.values: dict[tuple[str, tuple], float] = {}
        self.guard = threading.Lock()

    def inc(self, name: str, value: float = 1.0, **labels) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self.guard:
            self.values[key] = self.values.get(key, 0.0) + value

    def render(self, gauges: dict[str, float] | None = None) -> str:
        lines = []
        with self.guard:
            items = sorted(self.values.items())
        for (name, labels), value in items:
            label_text = ",".join(f'{k}="{v}"' for k, v in labels)
            lines.append(f"{name}{{{label_text}}} {value}" if label_text else f"{name} {value}")
        for name, value in (gauges or {}).items():
            lines.append(f"{name} {value}")
        return "\n".join(lines) + "\n"


metrics = Metrics()
