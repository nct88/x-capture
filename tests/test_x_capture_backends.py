#!/usr/bin/env python3
"""Kiểm tra nhận diện compositor, bind phím, backend chụp — không cần GUI."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from xcapture import desktop_keys, session  # noqa: E402
from xcapture.desktop_keys import gtk_binding, hypr_line, sway_line, command_for  # noqa: E402

try:
    import PyQt6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


class Session(unittest.TestCase):
    def test_niri_socket(self):
        with mock.patch.dict(os.environ, {"NIRI_SOCKET": "/run/user/1000/niri.sock",
                                          "XDG_CURRENT_DESKTOP": ""}, clear=False):
            self.assertTrue(session.is_niri())
            self.assertTrue(session.is_wlroots())

    def test_wayland_from_session_type(self):
        with mock.patch.dict(os.environ, {"XDG_SESSION_TYPE": "wayland",
                                          "WAYLAND_DISPLAY": "wayland-0"}, clear=False):
            self.assertTrue(session.is_wayland())

    def test_package_manager_void_alpine(self):
        self.assertIn("xbps", session.INSTALL)
        self.assertIn("apk", session.INSTALL)
        self.assertIn("grim", session.PACKAGES)


class Bindings(unittest.TestCase):
    def test_gtk_print(self):
        self.assertEqual(gtk_binding("Print"), "Print")
        self.assertEqual(gtk_binding("Ctrl+Print"), "<Control>Print")
        self.assertEqual(gtk_binding("Ctrl+Shift+Print"), "<Control><Shift>Print")
        self.assertEqual(gtk_binding("Meta+Print"), "<Super>Print")
        self.assertEqual(gtk_binding("Alt+Print"), "<Alt>Print")

    def test_hypr_and_sway_lines(self):
        self.assertEqual(hypr_line("Print", "x-capture --fullscreen"),
                         "bind = , PRINT, exec, x-capture --fullscreen")
        self.assertEqual(hypr_line("Ctrl+Print", "x-capture --rect"),
                         "bind = CTRL, PRINT, exec, x-capture --rect")
        self.assertEqual(hypr_line("Meta+Print", "x-capture --repeat"),
                         "bind = SUPER, PRINT, exec, x-capture --repeat")
        self.assertEqual(sway_line("Ctrl+Print", "x-capture --rect"),
                         "bindsym Ctrl+Print exec x-capture --rect")
        self.assertEqual(sway_line("Meta+Print", "x-capture --repeat"),
                         "bindsym Mod4+Print exec x-capture --repeat")

    def test_command_for(self):
        self.assertEqual(command_for("/usr/bin/x-capture", "rect"),
                         "/usr/bin/x-capture --rect")
        self.assertEqual(command_for("x-capture", "fullscreen"),
                         "x-capture --fullscreen")

    def test_hyprland_writes_snippet_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / ".config"
            with mock.patch.dict(os.environ, {"HOME": tmp, "XDG_CONFIG_HOME": str(cfg),
                                              "XDG_CURRENT_DESKTOP": "Hyprland",
                                              "HYPRLAND_INSTANCE_SIGNATURE": "sig"}):
                (cfg / "hypr").mkdir(parents=True)
                (cfg / "hypr" / "hyprland.conf").write_text("monitor=,preferred,auto,1\n")
                r = desktop_keys.bind_hyprland("x-capture", {"fullscreen": "Print", "rect": "Ctrl+Print"})
                self.assertTrue(r["fullscreen"])
                text = (cfg / "hypr" / "x-capture.conf").read_text()
                self.assertIn("bind = , PRINT, exec, x-capture --fullscreen", text)
                self.assertIn("bind = CTRL, PRINT, exec, x-capture --rect", text)
                main = (cfg / "hypr" / "hyprland.conf").read_text()
                self.assertIn("source = ~/.config/hypr/x-capture.conf", main)
                desktop_keys.unbind_hyprland()
                self.assertFalse((cfg / "hypr" / "x-capture.conf").exists())
                self.assertNotIn("x-capture-begin", (cfg / "hypr" / "hyprland.conf").read_text())

    def test_sway_and_niri_snippets(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / ".config"
            with mock.patch.dict(os.environ, {"HOME": tmp, "XDG_CONFIG_HOME": str(cfg)}):
                r = desktop_keys.bind_sway("x-capture", {"fullscreen": "Print"})
                self.assertTrue(r["fullscreen"])
                self.assertIn("bindsym Print exec",
                              (cfg / "sway" / "x-capture.conf").read_text())
                r = desktop_keys.bind_niri("x-capture", {"rect": "Ctrl+Print"})
                self.assertTrue(r["rect"])
                kdl = (cfg / "niri" / "x-capture.kdl").read_text()
                self.assertIn("Ctrl+Print", kdl)
                self.assertIn('spawn "x-capture" "--rect"', kdl)


@unittest.skipUnless(HAVE_QT, "PyQt6 required")
class GrabberSelect(unittest.TestCase):
    def test_x11_when_not_wayland(self):
        from xcapture.grabber import create_backend, X11Backend
        with mock.patch("xcapture.session.is_wayland", return_value=False):
            b = create_backend(mock.Mock())
            self.assertIsInstance(b, X11Backend)

    def test_niri_uses_grim_backend(self):
        from xcapture.grabber import create_backend, NiriBackend
        with mock.patch("xcapture.session.is_wayland", return_value=True), \
                mock.patch("xcapture.session.is_kde", return_value=False), \
                mock.patch("xcapture.session.is_niri", return_value=True), \
                mock.patch("xcapture.session.is_wlroots", return_value=True), \
                mock.patch("xcapture.grabber.shutil.which", side_effect=lambda c: c == "grim"), \
                mock.patch("xcapture.dbusutil.HAVE_QTDBUS", False):
            b = create_backend(mock.Mock())
            self.assertIsInstance(b, NiriBackend)

    def test_wayland_without_display_does_not_use_x11(self):
        from xcapture.grabber import create_backend, X11Backend, PortalBackend, WlrootsBackend
        env = {"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "wayland"}
        env = {k: v for k, v in env.items()}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch("xcapture.session.is_wayland", return_value=True), \
                mock.patch("xcapture.session.is_kde", return_value=False), \
                mock.patch("xcapture.session.is_niri", return_value=False), \
                mock.patch("xcapture.session.is_wlroots", return_value=False), \
                mock.patch("xcapture.grabber.shutil.which", return_value=None), \
                mock.patch("xcapture.dbusutil.HAVE_QTDBUS", True), \
                mock.patch("xcapture.portal.available", return_value=True), \
                mock.patch("xcapture.kde.kwin_available", return_value=False):
            os.environ.pop("DISPLAY", None)
            b = create_backend(mock.Mock())
            self.assertNotIsInstance(b, X11Backend)
            self.assertIsInstance(b, (PortalBackend, WlrootsBackend))


@unittest.skipUnless(HAVE_QT, "PyQt6 required")
class NiriWindows(unittest.TestCase):
    def test_parse_niri_json(self):
        from xcapture import grabber
        outputs = [{"logical": {"x": 0, "y": 0, "width": 1920, "height": 1080}}]
        windows = [{
            "title": "Kitty", "is_focused": True, "is_minimized": False,
            "layout": {"tile_pos_in_workspace_view": [10, 20], "window_size": [800, 600]},
        }]
        with mock.patch.object(grabber, "_json", side_effect=[outputs, windows]):
            vs, wins = grabber._niri_windows()
        self.assertEqual((vs.x(), vs.y(), vs.width(), vs.height()), (0, 0, 1920, 1080))
        self.assertEqual(len(wins), 1)
        r, title, active = wins[0]
        self.assertEqual(title, "Kitty")
        self.assertTrue(active)
        self.assertEqual((r.x(), r.y(), r.width(), r.height()), (10, 20, 800, 600))


if __name__ == "__main__":
    unittest.main(verbosity=2)
