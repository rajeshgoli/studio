"""python -m server [--port 8450 | --launchd-socket http]."""
import argparse

from .app import StudioServer
from .launchd import activate_socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--port", type=int, default=8450)
    group.add_argument("--launchd-socket")
    parser.add_argument("--idle-exit-secs", type=float, default=3600,
                        help="quiet seconds before exit; zero disables idle exit")
    args = parser.parse_args()
    if args.idle_exit_secs < 0:
        parser.error("--idle-exit-secs must be nonnegative")
    listener = activate_socket(args.launchd_socket) if args.launchd_socket else None
    with StudioServer(("127.0.0.1", args.port), listener=listener,
                      idle_exit_secs=args.idle_exit_secs) as server:
        print(f"Studio listening on 127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
