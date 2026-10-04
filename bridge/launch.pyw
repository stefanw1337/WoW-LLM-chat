"""Windowless launcher with a single-instance lock and visible startup errors."""
import ctypes
import msvcrt
from pathlib import Path
import sys
import traceback

folder = Path(__file__).resolve().parent


def alert(message):
    ctypes.windll.user32.MessageBoxW(None, message, "WoW LLM Chat", 0x10)


def launch():
    try:
        lock = (folder / '.bridge.lock').open('a+b')
        if lock.seek(0, 2) == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        alert('The bridge is already running, or its folder is not writable. Close the existing bridge before starting another.')
        return
    try:
        with (folder / 'bridge.log').open('a', encoding='utf-8', buffering=1) as log:
            sys.stdout = sys.stderr = log
            try:
                from bridge import main
                main()
            except SystemExit as error:
                if error.code:
                    alert('The bridge could not start. Check bridge/bridge.log for details, or run Setup.cmd if the addon is not installed.')
            except Exception as error:
                traceback.print_exc()
                alert(str(error) + '\n\nDetails are available in bridge/bridge.log.')
    finally:
        lock.close()


if __name__ == '__main__':
    launch()
