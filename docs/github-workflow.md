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

Bộ kiểm thử toàn dự án đã chạy thành công trên database thử nghiệm:

```powershell
python manage.py test --noinput
```

Ngày 12/11/2026: cả 277 test đều đạt sau khi đổi tên app và sửa lỗi nghỉ phép.
Backend chặn tự duyệt/từ chối đơn của chính mình; bộ lọc không hợp lệ trả danh sách rỗng.
Kiểm thử đã được cập nhật theo tab cá nhân/quản lý, trang chi tiết và phân trang hiện tại.

## Làm việc nhóm

- Commit và push lên nhánh riêng; mở Pull Request để nhóm xem trước khi gộp vào main.
- Không force-push main hoặc xóa migration đã chia sẻ.
- Không commit .venv, .idea, db.sqlite3, .env, media, references hoặc .local-backups.
- Dùng DJANGO_SECRET_KEY qua biến môi trường khi triển khai; giá trị mặc định chỉ dành cho chạy local.
- Không chạy migration hoặc lệnh tạo/xóa dữ liệu trên database chung khi chưa thống nhất với nhóm.
