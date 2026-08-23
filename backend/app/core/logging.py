import logging
import sys

_EXTRA_FIELDS = set()


class StructuredFormatter(logging.Formatter):
    """Key=value structured logs, e.g. `INFO scraper.success source=fed articles=17`."""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.levelname} {record.name}"
        msg = record.getMessage()
        extras = []
        for key, value in record.__dict__.items():
            if key in _EXTRA_FIELDS or key.startswith("_"):
                continue
            if key in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName", "taskName",
            }:
                continue
            extras.append(f"{key}={value}")
        line = f"{base} {msg}"
        if extras:
            line += " " + " ".join(extras)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class StructuredLogger:
    """Logger that accepts arbitrary key=value kwargs merged into the log line."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _emit(self, level: int, msg: str, kwargs: dict) -> None:
        if self.logger.isEnabledFor(level):
            self.logger.log(level, msg, extra=kwargs)

    def debug(self, msg: str, **kwargs) -> None:
        self._emit(logging.DEBUG, msg, kwargs)

    def info(self, msg: str, **kwargs) -> None:
        self._emit(logging.INFO, msg, kwargs)

    def warn(self, msg: str, **kwargs) -> None:
        self._emit(logging.WARNING, msg, kwargs)

    warning = warn

    def error(self, msg: str, **kwargs) -> None:
        self._emit(logging.ERROR, msg, kwargs)

    def exception(self, msg: str, **kwargs) -> None:
        self.logger.exception(msg, extra=kwargs)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(logging.getLogger(name))
