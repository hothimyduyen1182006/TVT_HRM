# Lấy hồ sơ và tài khoản TVT về máy

Chạy trong thư mục dự án với môi trường Python của PyCharm:

```powershell
git pull origin main
python manage.py migrate
python manage.py import_tvt_profiles --dry-run
python manage.py import_tvt_profiles --reset-passwords
```

Lệnh cuối hỏi mật khẩu hai lần, không hiển thị khi nhập. Dùng mật khẩu đã thống nhất trong nhóm. Không cần nhập hay chia sẻ mật khẩu quản trị.

Nếu muốn giữ mật khẩu các tài khoản đã có, bỏ `--reset-passwords`. Khi cần tạo tài khoản mới, lệnh vẫn hỏi mật khẩu cho tài khoản mới. Chạy lại không tạo thêm nhân viên, bằng cấp hoặc hợp đồng trùng.

| Mã nhân viên | Tên đăng nhập | Vai trò |
|---|---|---|
| NV01 | hothimyduyen | Nhân viên |
| NV02 | quanlyphongban | Trưởng phòng Sản xuất |
| NV03 | leduy | Nhân viên |
| NV04 | phamnhi | Nhân viên |
| NV05 | quanlynhansu | Nhân sự |
| NV06 | danghuy | Nhân viên |
| NV07 | buinam | Nhân viên |
| NV08 | giamdoc | Giám đốc |

Lệnh nhập thông tin cá nhân, email, chức vụ, bằng cấp, hợp đồng và phòng ban. Mã cũ dạng `DEMO-NV01`, `DEMO-MKT` được nhận diện để cập nhật đúng bản ghi và tên đăng nhập mới. Nếu tên đăng nhập hoặc số điện thoại thuộc người khác, lệnh dừng và hoàn tác toàn bộ, không gộp hay xóa tài khoản.

Database SQLite được sao lưu tự động vào `.local-backups` trước khi ghi. Tài khoản quản trị, file đính kèm hiện có và dữ liệu chấm công/lương không bị xóa. Không tự tính, duyệt hoặc chi trả lương; không thay chính sách OT.

NV05 giữ ngày vào làm 01/09/2026 và hợp đồng đến 31/08/2027. NV08 giữ lương cơ bản 20.000.000 và lương hợp đồng 11.500.000 theo dữ liệu đã cung cấp; chưa có chức vụ. Xếp loại được ghi cùng tên bằng vì chưa có trường riêng.

File JSON không có mật khẩu/hash, tài khoản quản trị, CCCD hoặc đường dẫn tài liệu riêng tư. Mật khẩu nhập trên máy nhận được băm bằng Django. Database thật và các file sao lưu không được đưa lên Git.
