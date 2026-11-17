# Lấy bản cập nhật phần thưởng ngày 17/11/2026

Nhánh: `feature/bonus-workflow-20261117`.
Nhánh được tạo từ `origin/main` tại commit `7bf8825`, sau đó ghép thay đổi phần thưởng.
Không đẩy database, môi trường ảo hoặc dữ liệu cá nhân lên cùng bản cập nhật này.

## Máy đã có repository

Chạy `git status` trước. Nếu có thay đổi chưa commit, hãy commit trên nhánh riêng
hoặc cất bằng `git stash push -u` trước khi đổi nhánh; không ghi đè file đang làm.
Sau đó chạy:

```powershell
git fetch origin
git switch --track origin/feature/bonus-workflow-20261117
```

Nếu đã có nhánh này trên máy, dùng:

```powershell
git switch feature/bonus-workflow-20261117
git pull --ff-only origin feature/bonus-workflow-20261117
```

## Máy chưa có repository

```powershell
git clone --branch feature/bonus-workflow-20261117 https://github.com/hothimyduyen1182006/TVT_HRM.git
cd TVT_HRM
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Máy đã có môi trường ảo thì kích hoạt môi trường của dự án trước khi chạy các
lệnh bên dưới. Dùng Python 3.12 để khớp môi trường đã kiểm tra.

## Cài đặt và khởi động

Dừng server. Sao lưu database trên máy nhận trước khi chạy migration:

```powershell
if (Test-Path -LiteralPath 'db.sqlite3') {
    $bonusBackupName = 'db-before-bonus-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.sqlite3'
    Copy-Item -LiteralPath 'db.sqlite3' -Destination $bonusBackupName
}
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test thuong --noinput
python manage.py runserver
```

Không dùng `migrate --fake` hoặc xóa migration để bỏ qua lỗi dữ liệu cũ. Nếu
migration báo dữ liệu không hợp lệ, giữ bản sao lưu và đối chiếu thông báo trước.
Database mới cần tài khoản, nhóm quyền và hồ sơ nhân viên phù hợp để sử dụng
chức năng; có thể tạo tài khoản quản trị bằng `python manage.py createsuperuser`.

## Nội dung và kết quả kiểm tra

- Chuyển xử lý thưởng từ views sang các service hiện có.
- Thêm đề xuất trùng tên sẽ báo lỗi, không ghi đè đề xuất đã có.
- Xuất CSV yêu cầu tháng/năm cụ thể và bộ lọc trạng thái Đã duyệt.
- Xuất giữ tiếng Việt và xử lý ô văn bản có thể bị hiểu thành công thức.
- Cập nhật test thưởng theo model tổng hợp/chốt công và luồng lương hiện tại.
- `manage.py check`: thành công.
- `manage.py makemigrations --check --dry-run`: không phát sinh migration.
- `manage.py test thuong --noinput`: 19 test thành công, có tạo database kiểm thử mới.

Bộ test công/lương chạy cùng lúc trước đó có lỗi ngoài phạm vi phần thưởng
(thiết lập nhóm quyền, kỳ vọng schema/lương cũ, kiểu dữ liệu và hoàn tác migration).
Không coi kết quả kiểm thử thưởng là xác nhận toàn bộ dự án đã hết lỗi.
Xung đột khi ghép với thay đổi riêng chưa công bố trên máy khác vẫn cần được
giải quyết theo nội dung; không dùng force push để bỏ qua.
