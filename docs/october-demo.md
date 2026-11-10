> Quy định hiện hành: OT tự động cho mọi phòng ban từ chấm công; không gửi/duyệt OT. Ngày thường tính sau 17:00; xem README.md để biết ngày nghỉ/lễ, giới hạn và dữ liệu lịch sử. Các mô tả duyệt OT bên dưới chỉ là lịch sử.

# Lấy code và bộ dữ liệu tháng 10/2026

```powershell
git pull origin main
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_october
.\.venv\Scripts\python.exe manage.py runserver
```

`seed_october` dùng khi database chưa có dữ liệu nghiệp vụ. Nếu muốn thay toàn bộ
dữ liệu nghiệp vụ hiện tại bằng bộ demo, chạy:

```powershell
.\.venv\Scripts\python.exe manage.py seed_october --reset
```

`--reset` sao lưu SQLite vào `.local-backups/` trước khi xóa dữ liệu nghiệp vụ.
Giữ nguyên tài khoản, mật khẩu và nhóm quyền hiện có. Tài khoản demo còn thiếu
được tạo mới; mật khẩu cho tài khoản mới chỉ in ra Terminal khi chạy lệnh.
Database, mật khẩu và bản sao lưu không đưa lên GitHub.

Bộ mẫu chỉ có kỳ 10/2026: 8 nhân viên, 7 phòng ban, 176 bản ghi chấm công,
8 phiếu lương, 16 khoản thưởng, OT, 5 đơn nghỉ phép, chức vụ và hợp đồng.
Lương ở trạng thái đã chi trả là mô phỏng, không có giao dịch thanh toán thật.
Các mức bảo hiểm và thuế chỉ là dữ liệu minh họa để xem giao diện.

Chọn tháng 10, năm 2026 trên Bảng công/Bảng lương/Bảng thưởng. Dashboard chọn
một ngày làm việc trong tháng 10/2026, ví dụ 01/10/2026, để xem thống kê công.
