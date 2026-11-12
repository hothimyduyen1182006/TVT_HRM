# Bộ dữ liệu minh họa TVT

Đã tạo 8 nhân viên và 7 phòng ban, đều đánh dấu DEMO. Không dùng số liệu này làm công,
lương, thuế hoặc bảo hiểm thật. Tài khoản demo không được cấp staff/superuser; tài khoản
quản trị hiện có giữ nguyên. Mật khẩu chung được sinh ngẫu nhiên khi chạy seed_demo lần đầu
và được cung cấp trong phản hồi của trợ lý, không lưu vào source code.

## Tài khoản để thử

| Tên đăng nhập | Vai trò | Phạm vi |
| --- | --- | --- |
| demo_employee | Nhân viên | Phiếu lương/công cá nhân DEMO-NV01 |
| demo_manager | Trưởng phòng | Hai nhân viên Phòng Sản xuất (DEMO) |
| demo_hr | Nhân sự | Công/lương của bộ demo, nhập đầu vào, tính, xuất theo quyền |
| demo_director | Giám đốc | Xem, duyệt và thao tác workflow theo quyền hiện có |
| demo_nv03, demo_nv04, demo_nv06, demo_nv07 | Nhân viên | Công/lương của từng người |

Đăng xuất tài khoản hiện tại trước khi thử tài khoản khác.

## Các kỳ minh họa

- 09/2026: công đã duyệt, lương đã duyệt; dùng xem chi tiết và xuất CSV/JSON/TXT.
- 10/2026: đã chi trả GIẢ LẬP; chứng từ mang mã DEMO, không phát sinh giao dịch thật.
- 11/2026: công đã được mở lại về chờ duyệt, lương đang chờ duyệt. Đăng nhập
  demo_hr, vào /bang_cong/?month=11&year=2026, chọn Xem chi tiết của một nhân viên rồi
  nhấn Duyệt bảng công cạnh Lịch sử điều chỉnh công. Chỉ nhân viên đó chuyển sang Đã duyệt.
  Sau khi duyệt công một nhân viên, bấm Tính lương để cập nhật phiếu của những người đã duyệt công,
  rồi dùng demo_director duyệt từng phiếu. Không cần chờ duyệt công toàn bộ nhân viên.
- 12/2026: không tạo dữ liệu, dùng xem giao diện trống.

Ví dụ: /bang_luong/?month=9&year=2026 và /bang_cong/?month=9&year=2026.
Nhân viên vào /bang_luong/ thấy phiếu cá nhân; tài khoản quản lý thấy bảng tổng hợp theo quyền.

Có công đủ ngày, đi muộn, nghỉ phép hưởng lương, nghỉ không lương, nghỉ không phép đã ghi
nhận rõ ràng, nghỉ nửa ngày và lịch sử sửa giờ vào. OT/thưởng gồm cả bản đã duyệt và chưa
duyệt để kiểm tra rằng chỉ phần được duyệt được cộng. Phụ cấp và hoàn ứng có căn cứ DEMO;
không sinh phạt đi muộn. Thuế và tỷ lệ BH là đầu vào giả lập đã đánh dấu, không phải chính sách.

Lịch demo sử dụng 08:00–17:00, nghỉ trưa 12:00–13:00, ngày thường thứ Hai–thứ Sáu và một
ngày lễ minh họa 02/09. Đây chỉ là cấu hình của dữ liệu mẫu, không thay đổi mặc định hệ thống.

## Chạy lại trên database mới

```powershell
python manage.py seed_demo
```

Lệnh tạo toàn bộ dữ liệu trong một transaction, dùng các service tính/duyệt hiện có.
Nếu bộ demo đã có, lệnh không tạo trùng hoặc đặt lại mật khẩu. Nếu có dữ liệu nhân viên
khác, tài khoản trùng hoặc lịch/kỳ mục tiêu đã tồn tại, lệnh dừng thay vì ghi đè.
Nếu quên mật khẩu demo, quản trị viên có thể dùng python manage.py changepassword <username>.

Database trước khi nạp đã được sao lưu trong .local-backups/db-before-demo-*.sqlite3.
Không phục hồi bản sao lưu đè database khi chưa xem xét các thay đổi phát sinh sau khi nạp.
