"""Gán phím tắt X-Capture qua cấu hình desktop khi không có kglobalaccel / XGrabKey.

Mỗi hành động gọi `x-capture --rect` (v.v.); phiên đang chạy nhận lệnh qua socket.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

ACTION_FLAGS = {
    "active": "--active",
    "window": "--window",
    "rect": "--rect",
    "freehand": "--freehand",
    "fullscreen": "--fullscreen",
    "scroll": "--scroll",
    "fixed": "--fixed",
    "repeat": "--repeat",
    "record": "--record",
    "color": "--color",
    "ocr": "--ocr",
}

MARK_BEGIN = "# x-capture-begin"
MARK_END = "# x-capture-end"
NIRI_BEGIN = "// x-capture-begin"
NIRI_END = "// x-capture-end"


def _desktops():
    return [d.strip().lower() for d in
            os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d.strip()]


def gtk_binding(seq: str) -> str:
    """Ctrl+Shift+Print -> <Control><Shift>Print"""
    if not seq:
        return ""
    parts = seq.split("+")
    if seq.endswith("++"):
        parts = seq[:-2].split("+") + ["plus"]
    mods = {
        "Ctrl": "Control", "Control": "Control", "Shift": "Shift",
        "Alt": "Alt", "Meta": "Super", "Super": "Super", "Win": "Super",
    }
    out = []
    key = "Print"
    for p in parts:
        if p in mods:
            out.append(f"<{mods[p]}>")
        else:
            key = p
    return "".join(out) + key


def command_for(exe: str, action: str) -> str:
    flag = ACTION_FLAGS.get(action)
    if not flag:
        return exe
    return f"{exe} {flag}"


def _run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5, **kw)
    except (OSError, subprocess.SubprocessError):
        return None


def _home():
    return Path(os.environ.get("HOME") or Path.home())


# ---------- GNOME / Cinnamon / MATE (gsettings) ----------
def _gsettings(*args):
    if not shutil.which("gsettings"):
        return None
    return _run(["gsettings", *args])


def bind_gnome(exe: str, mapping: dict) -> dict:
    results = {}
    if _gsettings("list-schemas") is None:
        return {a: False for a in mapping}
    schema = "org.gnome.settings-daemon.plugins.media-keys"
    paths = []
    for action, seq in mapping.items():
        if not seq:
            results[action] = True
            continue
        path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/x-capture-{action}/"
        paths.append(path)
        rel = schema + ".custom-keybinding:" + path
        ok = True
        for args in (
            ["set", rel, "name", f"X-Capture {action}"],
            ["set", rel, "command", command_for(exe, action)],
            ["set", rel, "binding", gtk_binding(seq)],
        ):
            r = _gsettings(*args)
            if r is None or r.returncode != 0:
                ok = False
        results[action] = ok
    listed = _gsettings("get", schema, "custom-keybindings")
    current = []
    if listed and listed.returncode == 0:
        current = re.findall(r"'([^']+)'", listed.stdout)
    for p in paths:
        if p not in current:
            current.append(p)
    # keep other custom keys, drop stale x-capture-* not in this mapping
    keep = [p for p in current if "/x-capture-" not in p or p in paths]
    formatted = "[" + ", ".join(f"'{p}'" for p in keep) + "]"
    _gsettings("set", schema, "custom-keybindings", formatted)
    return results


def unbind_gnome():
    listed = _gsettings("get", "org.gnome.settings-daemon.plugins.media-keys",
                        "custom-keybindings")
    if not listed or listed.returncode != 0:
        return
    current = re.findall(r"'([^']+)'", listed.stdout)
    keep = [p for p in current if "/x-capture-" not in p]
    formatted = "[" + ", ".join(f"'{p}'" for p in keep) + "]"
    _gsettings("set", "org.gnome.settings-daemon.plugins.media-keys",
               "custom-keybindings", formatted)


def gnome_screenshot_bindings():
    """Phím Print mặc định của GNOME Shell (Screenshots)."""
    if not shutil.which("gsettings"):
        return {}
    schema = "org.gnome.shell.keybindings"
    out = {}
    for key in ("screenshot", "show-screenshot-ui", "screenshot-window"):
        r = _gsettings("get", schema, key)
        if r and r.returncode == 0 and r.stdout.strip() not in ("@as []", "[]"):
            out[key] = r.stdout.strip()
    return out


def yield_gnome_print():
    """Gỡ Print khỏi GNOME Screenshots. Trả về bản sao lưu {key: value}."""
    binds = gnome_screenshot_bindings()
    for key, val in binds.items():
        _gsettings("set", "org.gnome.shell.keybindings", key, "[]")
    return binds


def restore_gnome_print(backup: dict):
    for key, val in backup.items():
        _gsettings("set", "org.gnome.shell.keybindings", key, val)


# ---------- XFCE (cũng dùng khi phiên XFCE Wayland) ----------
def bind_xfce(exe: str, mapping: dict) -> dict:
    results = {}
    if not shutil.which("xfconf-query"):
        return {a: False for a in mapping}
    for action, seq in mapping.items():
        if not seq:
            results[action] = True
            continue
        prop = "/commands/custom/" + gtk_binding(seq)
        r = _run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts",
                  "-p", prop, "-n", "-t", "string", "-s", command_for(exe, action)])
        results[action] = bool(r and r.returncode == 0)
    return results


# ---------- Hyprland ----------
def hypr_line(seq: str, cmd: str) -> str:
    parts = seq.split("+")
    mods, key = [], "PRINT"
    names = {"Ctrl": "CTRL", "Shift": "SHIFT", "Alt": "ALT",
             "Meta": "SUPER", "Super": "SUPER", "Win": "SUPER"}
    for p in parts:
        if p in names:
            mods.append(names[p])
        else:
            key = p.upper()
    mod = " ".join(mods)
    return f"bind = {mod}, {key}, exec, {cmd}"


def _hypr_conf_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "hypr"


def bind_hyprland(exe: str, mapping: dict) -> dict:
    lines = [MARK_BEGIN, "# managed by X-Capture — do not edit"]
    results = {}
    for action, seq in mapping.items():
        if not seq:
            results[action] = True
            continue
        lines.append(hypr_line(seq, command_for(exe, action)))
        results[action] = True
    lines.append(MARK_END)
    d = _hypr_conf_dir()
    d.mkdir(parents=True, exist_ok=True)
    snippet = d / "x-capture.conf"
    snippet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    main = d / "hyprland.conf"
    source = "source = ~/.config/hypr/x-capture.conf"
    _ensure_marked_block(main, f"{MARK_BEGIN}\n{source}\n{MARK_END}\n")
    return results


def unbind_hyprland():
    d = _hypr_conf_dir()
    try:
        (d / "x-capture.conf").unlink()
    except FileNotFoundError:
        pass
    _strip_marked_block(d / "hyprland.conf")


# ---------- Sway ----------
def sway_line(seq: str, cmd: str) -> str:
    parts = seq.split("+")
    names = {"Ctrl": "Ctrl", "Shift": "Shift", "Alt": "Mod1",
             "Meta": "Mod4", "Super": "Mod4", "Win": "Mod4"}
    keys = []
    for p in parts:
        keys.append(names.get(p, p))
    return f"bindsym {'+'.join(keys)} exec {cmd}"


def bind_sway(exe: str, mapping: dict) -> dict:
    lines = [MARK_BEGIN]
    results = {}
    for action, seq in mapping.items():
        if not seq:
            results[action] = True
            continue
        lines.append(sway_line(seq, command_for(exe, action)))
        results[action] = True
    lines.append(MARK_END)
    d = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "sway"
    d.mkdir(parents=True, exist_ok=True)
    snippet = d / "x-capture.conf"
    snippet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    main = d / "config"
    include = "include ~/.config/sway/x-capture.conf"
    _ensure_marked_block(main, f"{MARK_BEGIN}\n{include}\n{MARK_END}\n")
    return results


def unbind_sway():
    d = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "sway"
    try:
        (d / "x-capture.conf").unlink()
    except FileNotFoundError:
        pass
    _strip_marked_block(d / "config")


# ---------- niri ----------
def niri_bind(seq: str, exe: str, action: str) -> str:
    parts = seq.split("+")
    names = {"Ctrl": "Ctrl", "Shift": "Shift", "Alt": "Alt",
             "Meta": "Super", "Super": "Super", "Win": "Super"}
    keys = [names.get(p, p) for p in parts]
    flag = ACTION_FLAGS.get(action, "")
    spawn = f'spawn "{exe}"'
    if flag:
        spawn = f'spawn "{exe}" "{flag}"'
    return f'    {"+".join(keys)} {{ {spawn}; }}'


def bind_niri(exe: str, mapping: dict) -> dict:
    inner = [NIRI_BEGIN, "binds {"]
    results = {}
    for action, seq in mapping.items():
        if not seq:
            results[action] = True
            continue
        inner.append(niri_bind(seq, exe, action))
        results[action] = True
    inner += ["}", NIRI_END]
    d = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "niri"
    d.mkdir(parents=True, exist_ok=True)
    snippet = d / "x-capture.kdl"
    snippet.write_text("\n".join(inner) + "\n", encoding="utf-8")
    main = d / "config.kdl"
    include = f'{NIRI_BEGIN}\ninclude "x-capture.kdl"\n{NIRI_END}\n'
    _ensure_marked_block(main, include, begin=NIRI_BEGIN, end=NIRI_END)
    return results


def unbind_niri():
    d = Path(os.environ.get("XDG_CONFIG_HOME", _home() / ".config")) / "niri"
    try:
        (d / "x-capture.kdl").unlink()
    except FileNotFoundError:
        pass
    _strip_marked_block(d / "config.kdl", begin=NIRI_BEGIN, end=NIRI_END)


def _ensure_marked_block(path: Path, block: str, begin=MARK_BEGIN, end=MARK_END):
    text = ""
    if path.exists():
        text = path.read_text(encoding="utf-8", errors="replace")
    if begin in text and end in text:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end),
                      block.strip(), text, count=1, flags=re.S)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n" + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _strip_marked_block(path: Path, begin=MARK_BEGIN, end=MARK_END):
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"\n?" + re.escape(begin) + r".*?" + re.escape(end) + r"\n?",
                  "\n", text, count=1, flags=re.S)
    path.write_text(text, encoding="utf-8")


def compositor_family():
    """hyprland | sway | niri | gnome | cinnamon | mate | xfce | None"""
    from . import session
    if session.is_niri():
        return "niri"
    ds = set(_desktops())
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or "hyprland" in ds:
        return "hyprland"
    if os.environ.get("SWAYSOCK") or "sway" in ds:
        return "sway"
    if ds & {"gnome", "ubuntu", "unity", "pop", "zorin", "pantheon"}:
        return "gnome"
    if ds & {"x-cinnamon", "cinnamon"}:
        return "cinnamon"
    if "mate" in ds:
        return "mate"
    if "xfce" in ds:
        return "xfce"
    if session.is_wlroots():
        return "hyprland" if "hyprland" in ds else "sway"
    return None


def bind_all(exe: str, mapping: dict) -> dict:
    fam = compositor_family()
    if fam == "gnome":
        return bind_gnome(exe, mapping)
    if fam == "hyprland":
        return bind_hyprland(exe, mapping)
    if fam == "sway":
        return bind_sway(exe, mapping)
    if fam == "niri":
        return bind_niri(exe, mapping)
    if fam == "xfce":
        return bind_xfce(exe, mapping)
    if fam in ("cinnamon", "mate"):
        return bind_gnome(exe, mapping)
    return {a: False for a, seq in mapping.items() if seq}


def unbind_all():
    unbind_gnome()
    unbind_hyprland()
    unbind_sway()
    unbind_niri()
