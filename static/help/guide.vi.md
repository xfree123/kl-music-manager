# Hướng dẫn sử dụng KL Music Manager

KL Music Manager là trình phát nhạc và công cụ quản lý thư viện cho **iPod đời cũ** (Classic, Nano, Mini, Shuffle) và cho **thư mục nhạc trên máy tính**. Ứng dụng chạy hoàn toàn trên máy của bạn, không cần Internet và không gửi dữ liệu ra ngoài.

## Yêu cầu hệ thống {#requirements}

| Thành phần | Tối thiểu |
|---|---|
| Hệ điều hành (bản cài đặt) | Windows 10 hoặc Windows 11, 64-bit (x64) |
| Bộ nhớ trống | khoảng 450 MB sau khi cài (bộ cài 151 MB) |
| iPod | iPod dùng ổ USB (Classic, Nano 1–5G, Mini, Shuffle, Video), **định dạng cho Windows (FAT32)** |
| Chạy từ mã nguồn (chế độ trình duyệt) | Python 3.10 trở lên trên Windows, macOS hoặc Linux |

> macOS 13 Ventura trở lên được hỗ trợ khi tự build từ mã nguồn; bản 1.1.1 chỉ phát hành bộ cài Windows.

## Cài đặt {#install}

1. Chạy `KL-Music-Manager-Setup-1.1.1.exe`.
2. Windows có thể hiện cảnh báo SmartScreen vì bộ cài chưa được ký số: chọn **More info → Run anyway**.
3. Chọn thư mục cài đặt và hoàn tất. Mở ứng dụng từ Start menu: **KL Music Manager**.

## Bắt đầu nhanh

1. Cắm iPod và đợi iPod hiện thành một ổ đĩa trong File Explorer (với iPod đồng bộ iTunes cần bật *Enable disk use*).
2. Mở KL Music Manager. Ứng dụng tự tìm iPod; thanh trạng thái ở dưới hiện tên máy và số bài.
3. Nhấp đúp một bài để phát. Bấm **Now Playing** để xem ảnh bìa và spectrum.

Không có iPod? Dùng thư mục nhạc trên máy (xem phần tiếp theo) hoặc iPod ảo (tự tạo khi không tìm thấy iPod).

## Nguồn thư viện: iPod hoặc thư mục nhạc {#library}

Thẻ **Library** ở đầu cột phải cho biết nguồn đang dùng. Bấm **Change** (hoặc *Tools → Library Source…*, hoặc menu *Library → Open Music Folder…* / Ctrl+O):

- **iPod**: iPod đang cắm (hoặc đường dẫn iPod trong cài đặt).
- **Music folder**: một thư mục bất kỳ trên máy. Ứng dụng quét cả thư mục con, đọc tag (tên bài, nghệ sĩ, album…). Các file `.m3u` / `.m3u8` trở thành playlist. Thư mục đã mở gần đây được nhớ để chọn lại nhanh.

Lần quét đầu một thư mục lớn có thể mất một lúc; các lần sau dùng cơ sở dữ liệu thư viện và chỉ đọc file mới hoặc file đã đổi. Khi đổi về iPod, ứng dụng cần vài giây để đọc cơ sở dữ liệu của iPod.

### Nhiều thư viện {#libraries}

Mỗi thư mục nhạc bạn mở trở thành một **thư viện** trong danh sách **Libraries** ở cột phải (kèm số bài). Bấm vào thư viện để chuyển sang.

- **Default library** (thư viện mặc định) luôn nằm đầu danh sách: một iPod ảo trống trên máy (`virtual_ipod/` trong thư mục dữ liệu). Thư viện này không gỡ được, và là nơi ứng dụng quay về khi không có iPod hoặc khi bạn gỡ thư viện đang mở.
- Mục **iPod** chỉ hiện khi có iPod đang cắm.
- Nút **+** thêm một thư mục làm thư viện mới (quét ngay). Nút ⚙, *Tools → Manage Libraries…* hoặc menu *Library → Manage Libraries…* mở hộp **Libraries & Maintenance**.
- Trong hộp này: đổi tên thư viện (sửa tên rồi Enter), **Open** (mở), **Rescan** (đọc file mới / đã đổi / đã xoá), **Rebuild** (đọc lại tag mọi file), **Clear** (xoá metadata đã lập chỉ mục; lần quét sau đọc lại thư mục).
- **Gỡ thư viện** khỏi ứng dụng chỉ làm được ở tab [Manage](#manage) (nút **Remove**), để tránh bấm nhầm. Gỡ thư viện chỉ xoá mục đó và metadata trong cơ sở dữ liệu, không bao giờ xoá file nhạc. Gỡ thư viện đang mở thì ứng dụng chuyển về Default library.
- Tag và thông số file của mọi thư viện được lưu trong cơ sở dữ liệu trên máy (`library_cache/library.db`), nhờ đó mở thư mục lớn rất nhanh.

**Tools → Re-detect iPod / Rescan** đọc lại iPod hoặc quét lại thư mục (dùng khi bạn vừa cắm iPod, hoặc vừa chép thêm file vào thư mục).

## Duyệt nhạc (Browse, tag cloud) {#browse}

Tab **Browse** (Ctrl+B) nhóm thư viện đang mở thành đám mây thẻ: **Genres** (thể loại), **Artists** (nghệ sĩ), **Albums** (kèm ảnh bìa nhỏ), **Years** (năm) hoặc **Playlists**. Chữ càng to thì nhóm càng nhiều bài; rê chuột để xem số bài.

Bấm một mục để về bảng Library chỉ hiện các bài của mục đó. Cạnh số bài hiện chip như *Album: Nghe Mưa*; bấm **×** trên chip (hoặc chọn thể loại / playlist khác) để hiện lại tất cả. Thư viện rất lớn chỉ hiện 300 nhóm nhiều bài nhất.

## Chọn nhiều bài và xuất hàng loạt (Manage) {#manage}

Tab **Manage** (Ctrl+M) dùng để làm việc với nhiều bài cùng lúc. Nhạc vẫn phát bình thường khi bạn ở tab này.

- **Chọn bài**: bấm một dòng để chọn / bỏ chọn; giữ **Shift** rồi bấm dòng khác để chọn cả đoạn ở giữa. Ô vuông trên tiêu đề cột chọn / bỏ tất cả bài đang hiện; **Select shown** chọn mọi bài đang hiện (sau khi lọc), **Clear** bỏ chọn hết. Ô **Filter tracks…** lọc bảng giống ô tìm kiếm (không phân biệt dấu).
- **Chọn cả nhóm**: cột trái có các tab **Albums**, **Artists**, **Genres**, **Playlists**. Bấm một nhóm để chọn toàn bộ bài của nhóm, bấm lần nữa để bỏ. Ô vuông có dấu gạch nghĩa là nhóm mới được chọn một phần.
- Phía trên bảng hiện số bài đã chọn và tổng dung lượng.

**Export…** mở hộp xuất hàng loạt:

- **Format**: chọn **một định dạng cho cả danh sách** (Original, MP3, AAC, FLAC, ALAC, WAV, xem [Xuất bài hát](#export)), không chọn riêng từng bài.
- **Save to folder**: thư mục đích (mặc định là thư mục xuất trong Settings; **Choose…** để chọn thư mục khác).
- **Folders**: *Artist / Album* (mỗi nghệ sĩ một thư mục, trong đó mỗi album một thư mục) hoặc *All in one folder*. **Subfolder** (tuỳ chọn) đặt mọi file vào một thư mục con; khi bạn chọn đúng một playlist, ô này tự điền tên playlist.
- **Run at once**: số bài xử lý cùng lúc. Thư viện thư mục chạy được 1–4 bài song song (*Auto* = theo số nhân CPU, tối đa 4). Với iPod luôn là 1 bài một lúc, vì đọc song song từ iPod chỉ chậm hơn.
- **Skip files that already exist**: file cùng tên đã có ở thư mục đích thì bỏ qua (xuất lại sau khi bị ngắt sẽ chỉ làm phần còn thiếu). Tắt ô này thì file trùng tên được lưu thành `… (2)`.

Các bài được xếp thành **hàng đợi**: thanh tiến độ cho biết số bài đã xong và số bài đang chạy; bài lỗi hiện trong danh sách bên dưới và không làm dừng cả hàng đợi. **Cancel** dừng nhận bài mới (các bài đang chạy được làm xong). Khi xong, dòng tổng kết cho biết số bài đã xuất / bỏ qua / lỗi / huỷ; **Show Folder** mở thư mục xuất (thư mục đích + thư mục con).

Cột trái còn có danh sách **Libraries**: mở thư viện khác, **+ Add** thêm thư mục, **Remove** gỡ thư viện khỏi ứng dụng (không xoá nhạc).

## Tìm kiếm

Gõ vào ô **Search library…** (hoặc bấm `/` hay Ctrl+F). Tìm kiếm áp dụng cho **toàn bộ thư viện**, trên tên bài, nghệ sĩ, album, nghệ sĩ album, thể loại và nhạc sĩ.

- Không cần gõ dấu: `hong nhung` tìm ra *Hồng Nhung*.
- Nhiều từ là điều kiện "và": `trinh cong son khanh ly`.
- Enter: phát kết quả đầu tiên. Esc hoặc **Clear**: xoá tìm kiếm.

## Phát nhạc {#player}

Thanh trên cùng gồm: lùi bài / phát–tạm dừng / sang bài, ảnh bìa nhỏ, thanh thời gian, **Shuffle**, **Repeat** (tắt → lặp tất cả → lặp một bài), âm lượng.

- Nhấp đúp một bài để phát. Danh sách đang hiển thị (sau khi lọc, tìm, sắp xếp) trở thành hàng đợi phát.
- Hết bài sẽ tự sang bài tiếp theo.
- Bấm chuột phải vào bài → **Play Next** (phát ngay sau bài hiện tại) hoặc **Add to Queue** (thêm vào cuối hàng đợi).
- Phím media trên bàn phím và khung điều khiển nhạc của Windows hoạt động với ứng dụng.

**Now Playing** (nút ở thanh công cụ, phím `N`, hoặc bấm ảnh bìa nhỏ): ảnh bìa lớn trên nền mờ, cùng danh sách **Up Next**. Chọn chế độ hiển thị:

- **Cover**: ảnh bìa.
- **Spectrum**: phổ âm thanh theo thời gian thực. **Bars** / **Wave** đổi kiểu hiển thị.
- **Both**: ảnh bìa kèm phổ âm thanh.

Dưới tên bài, Now Playing hiện **thông tin file** của bài đang phát: codec (MP3, AAC, ALAC, FLAC, Vorbis, Opus, PCM, DTS), bitrate, sample rate, độ sâu bit (file lossless), số kênh và dung lượng file. Bản ngắn (codec · bitrate · sample rate) nằm ở bên phải thanh trên cùng; rê chuột vào để xem đầy đủ.

Ảnh bìa lấy theo thứ tự: ảnh nhúng trong file, ảnh `cover.jpg` / `folder.jpg` cùng thư mục, rồi ảnh bìa trong cơ sở dữ liệu iPod.

**Apple Lossless (ALAC)**: trình phát của ứng dụng không giải mã ALAC trực tiếp. Khi bật *Stream formats the player can't decode* (mặc định bật), ứng dụng tự chuyển sang FLAC để phát; lần đầu mỗi bài chờ khoảng 1 giây. Nếu tắt tuỳ chọn này, bài ALAC mở bằng trình phát mặc định của Windows.

**WAV chứa DTS** (đĩa "DTS-CD", album ghi `[DTS]`, `[DTS-ES]`): file khai là PCM nhưng bên trong là âm thanh vòm DTS, nên nếu phát trực tiếp chỉ nghe tiếng xèo xèo. Ứng dụng tự nhận ra, hiện codec *DTS* và chuyển sang FLAC stereo để phát (cùng tuỳ chọn trên).

**System Player**: bật công tắc này để mọi bài mở bằng trình phát mặc định của hệ điều hành.

## Phím tắt {#shortcuts}

| Phím | Chức năng |
|---|---|
| Space | Phát / tạm dừng |
| ← / → | Tua lùi / tới 5 giây |
| Ctrl+← / Ctrl+→ | Bài trước / bài sau |
| ↑ / ↓ | Tăng / giảm âm lượng |
| M | Tắt / bật tiếng |
| S | Bật / tắt Shuffle |
| R | Đổi chế độ Repeat |
| N | Chuyển Library ⇄ Now Playing |
| Ctrl+B | Mở Browse (tag cloud) |
| Ctrl+M | Mở Manage (chọn nhiều bài, xuất hàng loạt) |
| / hoặc Ctrl+F | Tìm kiếm |
| F1 | Mở hướng dẫn này |
| Ctrl+O | Mở thư mục nhạc |
| Ctrl+I / Ctrl+Shift+I | Nhập file / nhập cả thư mục |
| Ctrl+, | Cài đặt |

## Nhập nhạc (Import) {#import}

Bấm **Import** (hoặc kéo-thả file vào danh sách bài):

1. Chọn file (chọn được nhiều file). Trong ứng dụng desktop có thêm **Files…** và **Folder…** để chọn bằng hộp thoại của Windows; chọn thư mục sẽ nhập cả thư mục con.
2. **Add to playlist**: chọn playlist có sẵn, *+ New playlist…* để tạo mới, hoặc *None*.
3. Bấm **Import**. Danh sách bên dưới hiện kết quả từng file.

- Vào iPod: file được chép lên iPod và ghi vào cơ sở dữ liệu của iPod.
  - iPod phát được MP3, AAC, ALAC, WAV và AIFF; các file này được chép nguyên.
  - FLAC, OGG, Opus và WAV chứa DTS thì iPod không phát được, nên ứng dụng **tự chuyển định dạng** trước khi chép (cần ffmpeg, có sẵn trong bản cài). Mặc định nguồn lossless (FLAC) thành ALAC 16-bit, nguồn nén (OGG, Opus, DTS) thành AAC 256 kbps; tất cả về stereo, tối đa 48 kHz. Đổi cách chuyển trong [Settings](#settings).
  - Danh sách kết quả ghi rõ, ví dụ *imported (converted FLAC → ALAC)*. File gốc trên máy không bị thay đổi.
- Vào thư mục nhạc: file được chép vào `<thư mục>/<Nghệ sĩ>/<Album>/` theo tag.
- Khi nhập đúng một file, mục *Edit tags before import* cho phép sửa tag trước khi nhập.

> Sao lưu iPod trước khi ghi lần đầu. Chế độ chỉ đọc (Read-only) chặn mọi thao tác ghi.

## Playlist

- Tạo: nút **+** cạnh *Playlists*. Xoá: nút **×** cạnh tên playlist (file nhạc vẫn được giữ).
- Thêm bài: chuột phải → *Add to Playlist*. Xem bài thuộc playlist nào: chuột phải → *Show in Playlist*.
- Với thư mục nhạc, playlist được lưu thành file `.m3u8` trong `<thư mục>/Playlists/` (mở được bằng các trình phát khác).

## Sửa thông tin bài

Chuột phải → **Edit Metadata**. Với iPod, thay đổi ghi vào cơ sở dữ liệu iPod; với thư mục nhạc, thay đổi ghi thẳng vào tag của file. **Delete from iPod / Delete** xoá bài và file (có hỏi xác nhận).

- **Thư mục nhạc**: tên bài, nghệ sĩ, nghệ sĩ album, album, thể loại, nhạc sĩ, năm, bài số *n* trên *tổng*, đĩa số *n* trên *tổng*, BPM, ghi chú (comment) và lời bài hát (lyrics). Dùng được cho MP3, M4A (AAC / ALAC), FLAC, OGG, Opus, WAV, AIFF. Để trống một ô là xoá trường đó.
- **Ảnh bìa** (thư mục nhạc): **Choose image…** (JPEG, PNG…; thu nhỏ tối đa 1200 px, lưu dạng JPEG trong file) hoặc **Remove** (xoá). Đánh dấu **Apply to the whole album** để đổi cho mọi bài cùng album và cùng nghệ sĩ album. Thay đổi được ghi khi bấm **Save Changes**.
- **iPod**: tên bài, nghệ sĩ, nghệ sĩ album, album, thể loại, nhạc sĩ, năm, số bài và đánh giá (rating). Không sửa được ảnh bìa trên iPod.
- Cuối hộp thoại hiện thông số và đường dẫn của file.

## Xuất bài hát và chuyển định dạng {#export}

Chọn bài → **Export** (hoặc chuột phải → *Export to PC*):

| Định dạng | Ghi chú |
|---|---|
| Original | Chép nguyên file, không chuyển đổi |
| MP3 | 128–320 kbps |
| AAC (.m4a) | 128–320 kbps |
| FLAC | Lossless, mức nén 0–8 |
| ALAC (.m4a) | Apple Lossless |
| WAV | PCM 16-bit |

Có thể đổi sample rate (giữ nguyên, 44.1, 48 hoặc 96 kHz). Tag và ảnh bìa được giữ lại. Lưu vào **thư mục xuất** (mặc định `Nhạc\KL Music Manager`) hoặc chọn nơi lưu. Sau khi lưu, nút **Show** mở thư mục chứa file.

Muốn xuất nhiều bài, cả album hoặc cả playlist một lần: dùng tab [Manage](#manage).

## Xuất danh sách nhạc và thông tin thư viện

*Tools → Export Track List…* hoặc *Export Library Info…*:

- **Track list**: toàn bộ thư viện hoặc playlist đang chọn.
- **Library information**: thiết bị, tổng số bài / thời lượng / dung lượng, loại file, các playlist.
- Định dạng **HTML** (xem hoặc in bằng trình duyệt) hoặc **JSON** (dùng cho script, sao lưu).

## Cài đặt {#settings}

*Tools → Settings…* (Ctrl+,):

- **Export folder**: nơi lưu file xuất.
- **Default export format**, **Bitrate**, **Sample rate**, **FLAC compression**: giá trị mặc định trong hộp thoại xuất.
- **Read-only mode**: xem phần tiếp theo.
- **Stream formats the player can't decode**: phát ALAC và WAV chứa DTS bằng cách chuyển đổi tự động.
- **Importing into an iPod**: cách xử lý file iPod không phát được khi nhập vào iPod.
  - *Convert automatically* (mặc định): lossless thành ALAC, nén thành AAC.
  - *AAC 256 kbps*: phát được trên mọi iPod, kể cả Shuffle và Nano đời cũ vốn không phát ALAC.
  - *MP3 320 kbps*.
  - *ALAC*.
  - *Don't convert*: các file đó không được nhập.
- **ffmpeg path**: để trống là dùng ffmpeg đi kèm bộ cài.
- **Rescan libraries when the computer is idle** (mặc định tắt, chỉ bản desktop): khi máy không dùng đủ số phút đã đặt, ứng dụng quét lại mọi thư viện (chỉ file mới, đã đổi, đã xoá), tối đa một lần trong số giờ đã đặt. Danh sách bài tự cập nhật mà nhạc vẫn phát tiếp.

## Bảo trì (Maintenance) {#maintenance}

*Tools → Maintenance…* cho biết dung lượng cơ sở dữ liệu thư viện, bộ nhớ đệm ảnh bìa và bộ nhớ đệm phát nhạc.

- **Rescan all libraries now**: đọc file mới, đã đổi, đã xoá của mọi thư viện.
- **Clear cache**: xoá ảnh bìa đã đệm và các file FLAC tạm tạo ra để phát Apple Lossless (file đang phát được giữ lại).
- Theo từng thư viện (danh sách phía trên): **Rescan**, **Rebuild**, **Clear**; xem mục *Nhiều thư viện*.

## Chế độ chỉ đọc (Read-only) {#read-only}

Khi bật, ứng dụng **không ghi bất cứ thứ gì** vào iPod hoặc thư mục nhạc: các nút Import, Delete, sửa tag, tạo playlist bị ẩn và bị chặn cả ở phía máy chủ. Vẫn phát, tìm kiếm, xuất bài và đổi cài đặt được. Nên bật khi chỉ muốn nghe hoặc chép nhạc ra.

## Xử lý sự cố {#troubleshooting}

- **Không thấy iPod**: kiểm tra iPod đã hiện thành ổ đĩa trong File Explorer chưa, rồi chọn *Tools → Re-detect iPod*. iPod định dạng cho Mac (HFS+) không đọc được trên Windows.
- **Bài ALAC không phát trong ứng dụng**: bật *Stream formats the player can't decode* trong Settings.
- **File WAV chỉ nghe tiếng xèo xèo**: file chứa DTS. Bật tuỳ chọn trên. Nếu thư viện đã quét từ bản cũ, bấm *Rebuild* thư viện để thông tin file hiện đúng *DTS*.
- **Không xuất được MP3/FLAC… (needs ffmpeg)**: để trống *ffmpeg path* để dùng bản đi kèm, hoặc chỉ tới `ffmpeg.exe` của bạn.
- **Ứng dụng báo lỗi backend**: menu *Help → Open Backend Log*, gửi file log khi báo lỗi.
- **Quét thư mục lâu**: chỉ lần đầu; tag được lưu trong cơ sở dữ liệu thư viện cho các lần sau.
- **Tag sai hoặc cũ sau khi sửa file bằng chương trình khác**: *Tools → Maintenance…* → **Rescan** thư viện, hoặc **Rebuild** để đọc lại mọi file.

## Dữ liệu được lưu ở đâu {#data}

Mọi dữ liệu của ứng dụng nằm trong `%APPDATA%\KL Music Manager` (menu *Help → Open Data Folder*):

| Mục | Nội dung |
|---|---|
| `config.json` | Cài đặt |
| `library_cache/library.db` | Cơ sở dữ liệu thư viện: danh sách thư viện, tag và thông số file của các bài (SQLite) |
| `virtual_ipod/` | Default library (iPod ảo trên máy) |
| `stream_cache/` | Bản FLAC tạm để phát ALAC (tối đa 1 GB, tự dọn) |
| `device_cache.json` | Thông tin nhận diện iPod (giúp mở iPod nhanh hơn) |
| `logs/backend.log` | Nhật ký của phiên gần nhất |

Gỡ cài đặt không xoá thư mục này; xoá tay nếu muốn.

## Giấy phép {#license}

KL Music Manager là phần mềm tự do theo giấy phép **GNU GPL phiên bản 3 hoặc mới hơn**. Bộ cài kèm ffmpeg (GPLv3), Electron/Chromium và các thư viện mã nguồn mở khác; chi tiết trong `LICENSE` và `THIRD_PARTY_NOTICES.md`.
