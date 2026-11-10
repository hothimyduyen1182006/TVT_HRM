# Chia sẻ và làm việc với repository TVT HRM

Repository: https://github.com/hothimyduyen1182006/TVT_HRM

## Lấy bản hiện tại

Bản hiện tại nằm trên nhánh `main`, bao gồm phông chữ Inter, logo, OT tự động và bộ dữ liệu nhập phục vụ thực hành.

```powershell
git clone https://github.com/hothimyduyen1182006/TVT_HRM.git
cd TVT_HRM
```

Nếu đã clone và không có thay đổi chưa lưu:

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
```

Không chạy reset hoặc xóa thay đổi riêng để đổi nhánh. Nếu repository riêng tư, chủ repository cần cấp quyền cho thành viên.

## Khởi chạy

Làm theo README.md để tạo môi trường Python 3.12, cài requirements.txt, chạy migrate,
setup_roles, createsuperuser và runserver. Mỗi máy tự tạo database và tài khoản của mình.
Không có database thật, file tài liệu riêng tư hoặc mật khẩu/hash tài khoản trong repository. Có bộ hồ sơ được người dùng cung cấp và cho phép chia sẻ, kèm lệnh nhập đặt mật khẩu ngay trên máy nhận; xem [hướng dẫn nhập](shared-profiles.md).

OT hiện tại tính tự động từ chấm công, áp dụng mọi phòng ban; không gửi hoặc duyệt OT. Các nhánh về chính sách không tăng ca/OT Phòng Sản xuất chỉ là lịch sử. Không dùng chúng thay main để nhập bộ tình huống hiện tại.

## Kiểm thử và lưu ý

Bộ kiểm thử liên quan đã chạy thành công:

```powershell
python manage.py test attendance payroll config bonuses employees.test_personal_records employees.test_shared_profiles employees.tests.DemoDataTests.test_demo_login_and_personal_page --noinput
```

200 kiểm thử liên quan dùng database riêng đã chạy thành công sau khi ghép cập nhật mới nhất từ nhóm. Toàn bộ test suite còn các lỗi đã ghi nhận ngoài phần công/lương:
kiểm thử danh sách nghỉ phép đòi hiển thị lý do hiện nằm ở trang chi tiết; hai kiểm thử cũ trong
employees.tests.DemoDataTests chưa khớp cấu trúc context và điều hướng theo quyền hiện tại.

## Làm việc nhóm

- Commit và push lên nhánh riêng; mở Pull Request để nhóm xem trước khi gộp vào main.
- Không force-push main hoặc xóa migration đã chia sẻ.
- Không commit .venv, .idea, db.sqlite3, .env, media, references hoặc .local-backups.
- Dùng DJANGO_SECRET_KEY qua biến môi trường khi triển khai; giá trị mặc định chỉ dành cho chạy local.
- Không chạy migration hoặc lệnh tạo/xóa dữ liệu trên database chung khi chưa thống nhất với nhóm.
