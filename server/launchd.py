"""Adopt the listening socket supplied by macOS launchd."""
import ctypes
import os
import socket


def activate_socket(name):
    libc = ctypes.CDLL(None)
    activate = libc.launch_activate_socket
    activate.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.POINTER(ctypes.c_int)),
                         ctypes.POINTER(ctypes.c_size_t)]
    activate.restype = ctypes.c_int
    libc.free.argtypes = [ctypes.c_void_p]
    libc.free.restype = None
    fds = ctypes.POINTER(ctypes.c_int)()
    count = ctypes.c_size_t()
    error = activate(name.encode(), ctypes.byref(fds), ctypes.byref(count))
    if error:
        raise OSError(error, os.strerror(error))
    try:
        if not count.value:
            raise RuntimeError("launchd returned no sockets")
        first = fds[0]
        for index in range(1, count.value):
            os.close(fds[index])
        try:
            return socket.socket(fileno=first)
        except Exception:
            os.close(first)
            raise
    finally:
        libc.free(fds)
