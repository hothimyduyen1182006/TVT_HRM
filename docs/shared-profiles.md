# Lấy hồ sơ và tài khoản TVT về máy

## Cập nhật ngày 12/11/2026

Sau `git pull --ff-only origin main`, chạy `python manage.py migrate` và khởi động lại server.
Migration `employees.0005_shared_salary_settings` chuyển thiết lập từ đầu vào lương mới nhất sang từng nhân viên, giữ dữ liệu cũ.
HR cập nhật tại **Nhân viên → Sửa thông tin cơ bản → Thông tin thanh toán và bảo hiểm**, rồi chọn **Lưu thay đổi**.
Hồ sơ nhân viên và hồ sơ cá nhân chỉ hiển thị các ô đã khóa, không sửa trực tiếp.
Phụ cấp ăn trưa dùng chung theo nhân viên, mặc định 450.000đ/tháng; người phụ thuộc hiện cố định 0.
Các trường căn cứ, chế độ thuế và xác nhận trước đây đã ẩn khỏi giao diện, giữ giá trị đang lưu.
Các hướng dẫn cũ bên dưới về chọn lại chế độ thuế/phân loại phụ cấp theo kỳ không còn là thao tác trên giao diện hiện tại.

## Chuẩn bị dữ liệu trên máy nhận

Chạy trong thư mục dự án với môi trường Python của PyCharm:

```powershell
git pull origin main
python manage.py migrate
python manage.py import_tvt_profiles --dry-run
python manage.py import_tvt_profiles --reset-passwords
python manage.py prepare_october_training --dry-run
python manage.py prepare_october_training
```

Lệnh `import_tvt_profiles --reset-passwords` hỏi mật khẩu hai lần, không hiển thị khi nhập. Dùng mật khẩu đã thống nhất trong nhóm. Không cần nhập hay chia sẻ mật khẩu quản trị.

Hai lệnh `prepare_october_training` kiểm tra rồi chuẩn bị công, thưởng, phép và lương 10/2026: 177 bản ghi công, 19 khoản thưởng, 5 đơn phép, 8 đầu vào lương và 3 phiếu lương ở các trạng thái để thao tác thử. Không phiếu nào đã chi trả. Xem [hướng dẫn thực hành đầy đủ](october-testing.md).

Nếu tháng 10 trên máy nhận đã có dữ liệu khác, lệnh chuẩn bị sẽ dừng để bảo vệ dữ liệu đó; không tự xóa hoặc đặt lại. Nếu đã chạy thành công bộ tình huống này, chạy lại sẽ giữ nguyên các thao tác đã thực hiện.

Bản cập nhật mới bổ sung cột tiền tăng ca ở Bảng lương, cột giờ tăng ca trong chi tiết Bảng công, nút Lọc không có biểu tượng và tự tính thuế TNCN. Sau `migrate`, đầu vào cũ được giữ ở chế độ lịch sử: với phiếu chưa khóa, HR vào **Nhân viên → Hồ sơ → Thiết lập tính lương → Chỉnh sửa**, chọn chế độ cá nhân cư trú/hợp đồng từ 03 tháng, xác nhận giảm trừ và căn cứ; phiếu chưa duyệt tự cập nhật khi lưu hợp lệ. Phụ cấp ăn trưa 450.000đ cần chọn phân loại tiền ăn giữa ca bằng tiền. Phiếu đã duyệt/chi trả không tự thay đổi. Xem [hướng dẫn thuế](income-tax.md).

Git chia sẻ source, hồ sơ JSON và lệnh chuẩn bị dữ liệu; `git pull` không đồng bộ database hay các thao tác duyệt/chỉnh sửa đang có trên máy khác. Lệnh chuẩn bị tái tạo bộ tình huống ban đầu trên kỳ trống, không nhập đè trạng thái hiện tại của người nhận.

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
