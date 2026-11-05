# Đưa phần attendance/payroll vào repository nhóm

## Bản làm việc hiện tại

Thư mục này chưa có .git. ZIP trong references là bản tham khảo, không có lịch sử Git.
Không push nguyên thư mục này đè lên repository nhóm.

1. Trong PyCharm chọn Git > Clone, nhập URL repository nhóm và chọn thư mục mới.
   Tài khoản GitHub cần được chủ repository cấp quyền nếu repository riêng tư.
2. Trong bản clone, tạo nhánh feature/attendance-payroll từ main mới nhất.
3. Chép docs/integration-contract.md và docs/github-workflow.md vào nhánh.
4. Thống nhất requirements.txt dùng Django==4.2.8; giữ các thư viện khác nếu nhóm cần,
   không chép đè toàn bộ requirements hoặc settings của nhóm.
5. Dùng attendance đã có trong repository nhóm; không thêm timesheets.
6. Bổ sung services vào attendance và payroll khi triển khai; không chép đè app thành viên khác.
7. Review diff, commit tài liệu và gửi Pull Request để nhóm chốt giao tiếp dữ liệu.

## Mỗi lần hoàn thành chức năng

- Cập nhật main bằng Pull, rồi merge main vào nhánh của mình trước khi làm tiếp.
- Commit file thuộc phần mình, migration thật và kiểm thử liên quan.
- Push nhánh rồi mở Pull Request vào main; mô tả thay đổi, cách thử và phụ thuộc module khác.
- Không force-push main, không sửa/xóa migration người khác để xử lý xung đột.
- Không commit .venv, db.sqlite3, references, .env, media cá nhân hoặc khóa bí mật.
  .gitignore không tự bỏ theo dõi file đã được commit trước đó; kiểm tra diff trước khi push.
- Không chép SECRET_KEY từ settings hiện tại lên GitHub; phối hợp người quản lý cấu hình
  để dùng biến môi trường trước khi đưa thay đổi cấu hình lên repository nhóm.

## Chạy trong PyCharm

Chọn interpreter của dự án đã cài Django 4.2.8. Các lệnh dưới chạy trong Terminal của
bản clone đã cấu hình đúng interpreter:

```powershell
python -m django --version
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py runserver
```

Bản tích hợp hiện đã có model, migration và giao diện. Xem README.md cho thứ tự chạy
migrate, setup_roles, createsuperuser, cấu hình lịch và thử quy trình công/lương.
Không chạy migrate lên database chung trước khi review migration và có bản sao lưu.
