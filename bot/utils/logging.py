import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
	logger = logging.getLogger()
	logger.setLevel(level)

	if not logger.handlers:
		handler = logging.StreamHandler(stream=sys.stdout)
		formatter = logging.Formatter(
			fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
			datefmt="%Y-%m-%d %H:%M:%S",
		)
		handler.setFormatter(formatter)
		logger.addHandler(handler)
