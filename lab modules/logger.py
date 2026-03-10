# Centralized logging configuration
import logging
import logging.handlers
import queue

log_queue = queue.Queue(-1)
queue_handler = logging.handlers.QueueHandler(log_queue)
file_handler = logging.FileHandler("client.log")
formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")

file_handler.setFormatter(formatter)
listener = logging.handlers.QueueListener(log_queue, file_handler)
listener.start()

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(queue_handler)
logger.addHandler(console_handler)