# Chia sẻ và làm việc với repository TVT HRM

Repository: https://github.com/hothimyduyen1182006/TVT_HRM

## Lấy bản hiện tại

Bản hoàn thiện công/lương theo chính sách không tăng ca nằm trên nhánh `feature/tvt-hrm-no-overtime`.

```powershell
git clone --branch feature/tvt-hrm-no-overtime https://github.com/hothimyduyen1182006/TVT_HRM.git
cd TVT_HRM
```

Nếu đã clone và không có thay đổi chưa lưu:

```powershell
git fetch origin
git switch --track origin/feature/tvt-hrm-no-overtime
```

Nếu nhánh đã tồn tại trên máy, dùng `git switch feature/tvt-hrm-no-overtime`, sau đó `git pull --ff-only`.
Không chạy reset hoặc xóa thay đổi riêng để đổi nhánh. Nếu repository riêng tư, chủ repository cần cấp quyền cho thành viên.

## Khởi chạy

Làm theo README.md để tạo môi trường Python 3.12, cài requirements.txt, chạy migrate,
setup_roles, createsuperuser và runserver. Mỗi máy tự tạo database và tài khoản của mình.
Không có database, tài liệu nhân sự hoặc mật khẩu tài khoản cá nhân trong repository.

Bản OT Phòng Sản xuất đang được phát triển trên nhánh feature/production-overtime. Nhánh feature/tvt-hrm-no-overtime bên trên là bản đã chia sẻ trước đó; không nhầm hai chính sách. Chỉ clone nhánh production-overtime sau khi nhánh đã được push. Xem README.md để biết cấu hình và giới hạn mới.

## Kiểm thử và lưu ý

Bộ kiểm thử liên quan đã chạy thành công:

```powershell
python manage.py test attendance payroll config bonuses employees.test_personal_records employees.tests.DemoDataTests.test_demo_login_and_personal_page --noinput
```

168 kiểm thử dùng database riêng. Toàn bộ test suite còn các lỗi đã ghi nhận ngoài phần công/lương:
kiểm thử danh sách nghỉ phép đòi hiển thị lý do hiện nằm ở trang chi tiết; hai kiểm thử cũ trong
employees.tests.DemoDataTests chưa khớp cấu trúc context và điều hướng theo quyền hiện tại.

## Làm việc nhóm

- Commit và push lên nhánh riêng; mở Pull Request để nhóm xem trước khi gộp vào main.
- Không force-push main hoặc xóa migration đã chia sẻ.
- Không commit .venv, .idea, db.sqlite3, .env, media, references hoặc .local-backups.
- Dùng DJANGO_SECRET_KEY qua biến môi trường khi triển khai; giá trị mặc định chỉ dành cho chạy local.
- Không chạy migration hoặc lệnh tạo/xóa dữ liệu trên database chung khi chưa thống nhất với nhóm.
