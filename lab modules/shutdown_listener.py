import socket
from logger import logger
import os

# Define constants locally
SHUTDOWN_PORT = 6000
SHUTDOWN_PASSWORD = "nick"

def listen_for_shutdown():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('0.0.0.0', SHUTDOWN_PORT))
    sock.listen(1)
    
    while True:
        conn, addr = sock.accept()
        with conn:
            data = conn.recv(1024).decode().strip()
            if data == f"shutdown {SHUTDOWN_PASSWORD}":
                logger.info("Received valid shutdown command")
                os._exit(0)