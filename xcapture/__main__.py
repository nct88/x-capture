"""Điểm vào: nếu đã có phiên bản đang chạy thì chỉ gửi lệnh qua socket (không cần nạp Qt)."""
import os
import socket
import sys
import tempfile

USAGE = """X-Capture — screen capture for Linux

Usage: x-capture [option] [image files...]
  --active       capture the active window
  --window       capture a window / object (click to choose)
  --rect         capture a rectangular region
  --freehand     capture a freehand region
  --fullscreen   capture the full screen (all monitors)
  --scroll       capture a scrolling window
  --fixed        capture a fixed-size region
  --repeat       repeat the last capture
  --record       start / stop the screen recorder (needs ffmpeg)
  --color        screen color picker
  --ocr          capture text (needs tesseract)
  --editor       open the editor
  --panel        show the capture panel
  --settings     open settings
  --tray         start hidden in the system tray (or hide the running panel)
  --quit         quit the running instance
  --report       open the problem report form (nct88.dev/issues) with system info filled in
"""


def socket_path():
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(base, f"x-capture-{os.getuid()}.sock")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(USAGE)
        return 0
    if args == ["--cleanup"]:
        from .cleanup import main as cleanup
        return cleanup()
    if args == ["--report"]:
        from . import xapp_report
        from .version import VERSION
        url = xapp_report.report_url("x-capture", VERSION)
        print(url)
        return 0 if xapp_report.open_url(url) else 1
    args = [a if a.startswith("-") else os.path.abspath(a) for a in args]
    path = socket_path()
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(path)
        s.sendall("\n".join(args).encode() + b"\n")
        s.close()
        return 0
    except OSError:
        if args == ["--quit"]:
            return 0
    # lệnh dùng cho lối tắt tự khởi động: trình khởi chạy cạnh gói (bản cài) nếu không được truyền vào
    launcher = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "x-capture")
    exe = os.environ.get("XCAPTURE_EXE") or (launcher if os.access(launcher, os.X_OK) else "x-capture")
    from .app import run
    return run(args, path, exe)


if __name__ == "__main__":
    sys.exit(main())
