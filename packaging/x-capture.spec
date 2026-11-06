Name:           x-capture
Version:        1.2.0
Release:        1%{?dist}
Summary:        Screenshot tool (FastStone Capture style)
License:        LicenseRef-nct88
URL:            https://github.com/nct88/x-capture
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  desktop-file-utils
Requires:       python3 >= 3.10
%if 0%{?suse_version}
Requires:       python3-PyQt6
Requires:       python3-python-xlib
Recommends:     ffmpeg
Recommends:     tesseract-ocr
%else
Requires:       python3-pyqt6
Requires:       python3-xlib
Recommends:     xdotool
Recommends:     ffmpeg-free
Recommends:     tesseract
Recommends:     grim
%endif

%description
Floating capture toolbar, global hotkeys, annotating editor, pin-to-screen
and color picker. Works on X11 and Wayland (KWin ScreenShot2, grim,
xdg-desktop-portal).

%prep
%autosetup -n %{name}-%{version}

%build

%install
bash packaging/stage.sh %{buildroot}

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/x-capture.desktop

%files
%license packaging/copyright
%{_bindir}/x-capture
%{_datadir}/x-capture/
%{_datadir}/applications/x-capture.desktop
%{_datadir}/icons/hicolor/*/apps/x-capture.*

%changelog
* Fri Nov 06 2026 truongit <lienhe@truong.me> - 1.2.0-1
- Global hotkeys on GNOME/Hyprland/Sway/niri; niri window list; Wayland recording.
- Do not fall back to X11 capture on pure Wayland (black frames).

* Fri Nov 06 2026 truongit <lienhe@truong.me> - 1.1.0-1
- First packaged release for Debian, Fedora, openSUSE and Arch.
