# X-Capture

Công cụ chụp màn hình cho Linux, mô phỏng **FastStone Capture**: thanh công cụ chụp nổi, phím tắt toàn cục,
trình chỉnh sửa có chú thích, ghim ảnh lên màn hình và các công cụ màn hình. Chạy trên X11 (XFCE, MATE,
Cinnamon, KDE...) và Wayland (KDE Plasma, GNOME, Sway/Hyprland).


## Phím tắt trên mọi desktop (1.2.0)

- **X11 (XFCE, MATE, Cinnamon, i3):** XGrabKey như trước.
- **KDE Plasma:** kglobalaccel (Cài đặt hệ thống → Phím tắt → X-Capture).
- **GNOME Wayland:** GSettings custom-keybindings gọi x-capture --rect (v.v.). Có thể tắt phím Print của Ảnh chụp màn hình GNOME (gsettings schema org.gnome.shell.keybindings).
- **Hyprland:** ghi ~/.config/hypr/x-capture.conf và source trong hyprland.conf. Reload: hyprctl reload.
- **Sway:** ~/.config/sway/x-capture.conf được include vào config. Reload: swaymsg reload.
- **niri:** ~/.config/niri/x-capture.kdl + include. Reload compositor.

Chụp trên Wayland: KWin ScreenShot2, grim (Sway/Hyprland/niri), xdg-desktop-portal (GNOME). Không còn fallback X11 trên Wayland thuần (ảnh đen). Quay phim: GNOME Shell Screencast, Spectacle (KDE), wf-recorder, ffmpeg/x11grab.

Nix: 
ix run github:nct88/x-capture (flake.nix).

## Cài đặt

Gói sẵn: [Releases](https://github.com/nct88/x-capture/releases) (`.deb` / `.rpm` / Arch).


```bash
./install.sh
```

Bộ cài chép ứng dụng vào `~/.local/share/x-capture`, tạo lệnh `~/.local/bin/x-capture`, lối tắt trong menu
ứng dụng và biểu tượng. Phần này không cần quyền root. Thư viện cần có là PyQt6 và python-xlib; bộ cài tự chọn:

1. Máy đã có PyQt6 của hệ thống: dùng luôn.
2. Chưa có: hỏi có cài bằng trình quản lý gói không (cần sudo).
3. Không có sudo, hoặc chạy không có terminal: tải PyQt6 bằng `pip` (khoảng 80 MB) vào
   `~/.local/share/x-capture/venv`. Debian thiếu `python3-venv` thì giải nén gói `.deb` thay thế.

| Bản phân phối | Gói thư viện | Tuỳ chọn: quay phim · OCR |
|---|---|---|
| Debian / Ubuntu / Mint | `python3-pyqt6 python3-xlib` | `ffmpeg` · `tesseract-ocr tesseract-ocr-vie` |
| Fedora / RHEL | `python3-pyqt6 python3-xlib` | `ffmpeg-free` · `tesseract tesseract-langpack-vie` |
| Arch / Manjaro | `python-pyqt6 python-xlib` | `ffmpeg` · `tesseract tesseract-data-vie` |
| openSUSE | `python3-PyQt6 python3-python-xlib` | `ffmpeg` · `tesseract-ocr tesseract-ocr-traineddata-vietnamese` |

Tuỳ chọn của bộ cài: `--system` (bắt buộc dùng gói hệ thống), `--venv` (bắt buộc dùng pip), `--yes` (không hỏi).
Chạy lại `./install.sh` để cập nhật; sau khi nâng cấp Python của hệ thống, chạy lại để làm mới môi trường venv.

### Wayland

X-Capture vẫn chạy cửa sổ qua XWayland (lớp phủ chọn vùng, thanh nổi, ảnh ghim cần tự đặt vị trí), còn ảnh
màn hình và phím tắt đi qua trình tổng hợp:

| Desktop | Chụp màn hình | Phím tắt toàn cục | Bắt dính cửa sổ |
|---|---|---|---|
| KDE Plasma | KWin ScreenShot2 (≈0,1 s); dự phòng `spectacle` | kglobalaccel, hiện trong Cài đặt hệ thống → Phím tắt | KWin script |
| GNOME | xdg-desktop-portal (lần đầu hỏi quyền) | tự gán trong Cài đặt → Bàn phím tới lệnh `x-capture --rect`... | chỉ màn hình |
| Sway / Hyprland | `grim` | tự gán trong cấu hình tới lệnh `x-capture --rect`... | swaymsg / hyprctl |

KWin chỉ cho ứng dụng có khai báo trong tệp `.desktop` được chụp màn hình. Bộ cài tạo venv với bản **sao chép**
trình thông dịch (`--copies`) và ghi `X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2` cho đúng tệp
thực thi đó, nên quyền này không mở cho các chương trình Python khác.

Trên KDE, `Print`, `Shift+Print`, `Meta+Print` mặc định thuộc Spectacle. Trong **Cài đặt → Phím tắt** của
X-Capture có nút **Nhường các phím này cho X-Capture**; nút này sao lưu phím cũ để khôi phục sau.

Gỡ bỏ: `./install.sh --uninstall`. Lệnh này trả lại các phím tắt KDE / XFCE đã nhường và gỡ phím tắt của
X-Capture khỏi KDE, nhưng giữ lại cấu hình ở `~/.config/x-capture/x-capture.ini`.

## Thanh công cụ chụp (Capture Panel)

Từ trái sang phải: chụp cửa sổ đang hoạt động · chụp cửa sổ/đối tượng · vùng chữ nhật · vùng tự do ·
toàn màn hình · cửa sổ cuộn · vùng kích thước cố định · quay phim màn hình · nơi xuất ảnh
(trình chỉnh sửa / bộ nhớ tạm / tệp / ghim) · menu (hẹn giờ, kính lúp, thước, chọn màu, OCR, tự động chụp,
cài đặt). Kéo tay cầm bên trái để di chuyển; chuột phải lên thanh cũng mở menu.

Nút × (hoặc Alt+F4) trên thanh làm gì do **Cài đặt → Chung → Khi đóng thanh công cụ chụp** quyết định:

| Lựa chọn | Hành vi |
|---|---|
| Chạy ẩn ở khay hệ thống (mặc định) | Ẩn thanh, X-Capture tiếp tục chạy; phím tắt vẫn hoạt động. Bấm biểu tượng ở khay để hiện lại |
| Thoát X-Capture | Thoát hẳn (hỏi lưu các ảnh chưa lưu trong trình chỉnh sửa) |
| Luôn hỏi | Hỏi mỗi lần đóng, có ô "Ghi nhớ lựa chọn" |

Nếu không có khay hệ thống, X-Capture không ẩn thanh mà hỏi có thoát không. Khởi động ẩn ở khay:
bỏ chọn "Hiện thanh công cụ chụp khi khởi động" hoặc chạy `x-capture --tray` (lối tắt tự khởi động dùng lệnh
này). Với phiên đang chạy, `x-capture --tray` ẩn thanh xuống khay, `x-capture --panel` hiện lại.

Khi chọn vùng: kính lúp hiển thị toạ độ và mã màu, rê chuột lên một cửa sổ rồi bấm để chụp nguyên cửa sổ,
phím mũi tên dịch con trỏ 1 px (Shift: 10 px), Esc hoặc chuột phải để huỷ.

## Phím tắt mặc định

| Phím | Chức năng |
|---|---|
| `Alt+Print` | Chụp cửa sổ đang hoạt động |
| `Shift+Print` | Chụp cửa sổ / đối tượng |
| `Ctrl+Print` | Chụp vùng chữ nhật |
| `Ctrl+Shift+Print` | Chụp vùng tự do |
| `Print` | Chụp toàn màn hình |
| `Ctrl+Alt+Print` | Chụp cửa sổ cuộn |
| `Ctrl+Shift+Alt+Print` | Chụp vùng cố định |
| `Super+Print` | Lặp lại lần chụp trước |

Đổi trong **Cài đặt → Phím tắt** (trên KDE: xem mục Wayland ở trên). Trên XFCE, `Print`, `Alt+Print`, `Shift+Print` mặc định thuộc về
`xfce4-screenshooter`; X-Capture đánh dấu các phím đó là "bị chiếm" và có nút **Giải phóng phím Print
cho X-Capture** (sao lưu, có thể khôi phục).

Có thể gán phím trong cài đặt bàn phím của hệ thống tới các lệnh dòng lệnh. Lệnh gửi yêu cầu sang
phiên X-Capture đang chạy, hoặc tự khởi động một phiên mới nếu chưa có:

```bash
x-capture --rect
```

Các tuỳ chọn khác: `--active --window --freehand --fullscreen --scroll --fixed --repeat --record --color
--ocr --editor --panel --settings --tray --quit --report`, hoặc truyền đường dẫn ảnh để mở trong trình chỉnh sửa.

## Trình chỉnh sửa

* Nhiều thẻ, kéo thả ảnh, dán ảnh từ bộ nhớ tạm, hoàn tác / làm lại không giới hạn.
* Công cụ vẽ (sửa lại được: chọn, kéo, kéo tay cầm, đổi màu/độ dày): mũi tên, đường thẳng,
  hình chữ nhật, elip, bút vẽ, bút dạ quang, tô sáng vùng, chữ, khung chú thích, số thứ tự bước,
  làm mờ, làm vỡ hạt, đèn rọi (spotlight), cắt ảnh, lấy màu. Giữ Shift để vẽ thẳng 45° / hình vuông.
* Ảnh: đổi kích thước, xoay, lật, viền, đổ bóng, mép xé, thêm chú thích, ảnh xám, đảo màu.
* Lưu PNG, JPEG, BMP, WebP, TIFF, GIF, PDF; lưu nhanh với tên tự động (`Ctrl+Alt+S`); mở bằng trình
  sửa ảnh ngoài (mặc định `gimp %f`); ghim ảnh lên màn hình (`Ctrl+P`).

## Cấu trúc mã nguồn

```
x-capture            trình khởi chạy (shell)
install.sh           bộ cài cho người dùng hiện tại
data/                tệp .desktop và biểu tượng SVG
xcapture/
  __main__.py        điểm vào, gửi lệnh tới phiên đang chạy qua Unix socket
  app.py             điều phối: khay hệ thống, quy trình chụp, nơi xuất ảnh
  panel.py           thanh công cụ chụp nổi
  overlay.py         lớp phủ chọn vùng / cửa sổ / màu (có kính lúp)
  session.py         nhận diện X11 / Wayland, desktop, lệnh cài gói theo bản phân phối
  grabber.py         chụp màn hình theo phiên (X11 / KWin / grim / portal), danh sách cửa sổ, XTest
  kde.py             KWin ScreenShot2, danh sách cửa sổ qua KWin script, phím tắt kglobalaccel
  portal.py          chụp qua xdg-desktop-portal
  dbusutil.py        gọi D-Bus bằng QtDBus với kiểu dữ liệu tường minh
  hotkeys.py         phím tắt toàn cục: XGrabKey (X11) / kglobalaccel (KDE)
  cleanup.py         x-capture --cleanup: trả lại phím tắt khi gỡ cài
  editor.py          trình chỉnh sửa
  items.py           đối tượng chú thích và lệnh hoàn tác
  imageops.py        hiệu ứng ảnh, lưu tệp, đặt tên tự động
  tools.py           ghim ảnh, kính lúp, thước, chọn màu, OCR, chụp cuộn, quay phim
  settings_dialog.py cài đặt
  vi.py / i18n.py    giao diện tiếng Việt / English
```

## Giới hạn

* Wayland:
  * Kính lúp phóng to trên ảnh tĩnh vừa chụp, không cập nhật liên tục.
  * Chụp cuộn không tự lăn được cửa sổ của ứng dụng khác: bạn tự lăn chuột, X-Capture chụp liên tục và ghép.
  * Quay phim: KDE dùng chế độ quay vùng của Spectacle, Sway/Hyprland dùng `wf-recorder`.
  * GNOME không có cách bắt dính vào cửa sổ (chỉ bắt dính vào màn hình).
  * Màn hình nhiều mức thu phóng khác nhau có thể lệch vài điểm ảnh khi bắt dính cửa sổ.
* "Chụp đối tượng" trên Linux chỉ nhận được cửa sổ cấp cao nhất: ứng dụng GTK/Qt không tạo cửa sổ X
  riêng cho từng nút bấm như Windows.
* Chụp cuộn so khớp nội dung giữa các lần cuộn. Thanh tiêu đề hoặc chân trang cố định nằm trong vùng chọn
  có thể bị lặp lại, nên chỉ chọn phần nội dung cuộn.

## Báo lỗi / góp ý

Menu của thanh công cụ chụp (hoặc biểu tượng ở khay) có mục **Báo lỗi / góp ý...**; lệnh tương đương
`x-capture --report`. Mục này mở https://nct88.dev/issues với phiên bản X-Capture, distro, desktop và
X11/Wayland đã điền sẵn. Không có gì được gửi tự động: bạn xem lại form rồi mới bấm Gửi.
