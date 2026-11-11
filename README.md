## OT tự động từ chấm công

- Áp dụng tất cả phòng ban. Ngày làm việc: OT = max(0, check-out − max(17:00, check-in)), khi có bản ghi Có mặt hợp lệ và lịch ngày.
- Ngày nghỉ/lễ: tính giờ làm thực tế trừ nghỉ trưa; không sinh công thường. Hệ số ban ngày: 1,5 ngày thường; 2 nghỉ tuần; 3 lễ.
- Cùng một hàm `automatic_overtime()` phục vụ Bảng công, lịch sử chỉnh sửa và nguồn lương. Giờ OT là thuộc tính suy ra từ giờ vào/ra, giữ 4 chữ số thập phân; không cần cột mới, migration hoặc backfill.
- Không còn gửi yêu cầu, duyệt/từ chối hoặc quyền OT theo phòng. URL cũ trả 404. `OvertimeApproval` và cờ phòng cũ giữ trong schema để bảo toàn lịch sử, không tham gia tính; admin lịch sử chỉ đọc.
- Lương OT = lương giờ căn cứ HR xác nhận × giờ OT tự động × hệ số. Không tự dùng thưởng/tiền ăn làm căn cứ. Tính lại thay snapshot chờ duyệt; không cộng vào tiền OT đã lưu trước đó.
- Phiếu đã chi trả giữ nguyên snapshot. Phiếu cũ chưa chi trả có nguồn OT cũ cần mở lại theo quyền và tính lại trước khi duyệt/chi trả/xuất.
- Check-out thực tế không bị cắt. Vượt 50% giờ chuẩn/ngày, tổng 12 giờ/ngày, 40 giờ/tháng hoặc ngưỡng mặc định 200 giờ/năm được cảnh báo; không tự cắt giờ/tiền đã làm. Công ty cần kiểm tra điều kiện ngoại lệ 300 giờ nếu áp dụng.
- Ca qua ngày chưa được model chấm công hỗ trợ. Giờ ban đêm được giữ nguyên nhưng chặn tính lương thay vì áp sai hệ số ban ngày; chưa triển khai các khoản cộng thêm ban đêm.
- Tự động ghi nhận không thay thế yêu cầu đồng ý làm thêm và tổ chức lao động của công ty. Tham khảo Điều 98, 106, 107 [Bộ luật Lao động 2019](https://vanban.chinhphu.vn/?classid=1&docid=198540&pageid=27160&typegroupid=3).

# TVT HRM — Django 4.2.8

Bản tích hợp đồ án: nhân viên/phòng ban/tài khoản dùng Django Admin; bảng công và
bảng lương có giao diện Bootstrap, phân quyền backend, service, migration và kiểm thử.
OT tự động cho mọi phòng ban từ chấm công thực tế; không có quy trình đăng ký/phê duyệt OT.
Giữ dữ liệu OT cũ chỉ để đối chiếu lịch sử. Không tạo sẵn nhân viên
hoặc mật khẩu mẫu trong database thật.

## Chạy trên PyCharm / Windows

Mở thư mục có manage.py. Repo dùng Django 4.2.8; máy mới nên dùng Python 3.12 và cài requirements.txt.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py setup_roles
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Use Python 3.12 for this Django 4.2.8 project. Do not run it with Python 3.14.
Truy cập http://127.0.0.1:8000/ và đăng nhập tài khoản vừa tạo. Mở trang thưởng tại /bonuses/.
Quản trị tại /admin/; bảng công /attendance/; bảng lương /payroll/;
dữ liệu thuế/BH/phụ cấp /payroll/inputs/; nhân viên /employees/.
Bootstrap tải từ CDN, cần internet để hiển thị đầy đủ kiểu dáng; form vẫn hoạt động khi CDN không có mạng.

### Giao diện bảng công theo mẫu

- Nhân sự/Giám đốc/Trưởng phòng mở /attendance/ để xem tổng hợp một dòng mỗi nhân viên,
  tìm theo mã/họ tên và lọc phòng, trạng thái, tháng/năm trong phạm vi quyền.
- Chọn Xem chi tiết để mở /attendance/employee/<id>/ với chỉ số tháng và bảng từng ngày.
  Có lọc khoảng ngày, tình trạng, đi trễ/nghỉ phép/nghỉ không phép và phân trang.
- Nhân viên thông thường vào /attendance/ sẽ thấy giao diện công cá nhân.
- Lịch sử tại /attendance/employee/<id>/history/ hiển thị từng trường trước/sau, người sửa,
  lý do; lọc theo thời gian điều chỉnh, trường và người. Chỉ hiển thị lần sửa thực sự;
  không đưa tạo mới, lưu không đổi, duyệt hoặc tính lại tự động vào lịch sử điều chỉnh.
- Nhân sự/Giám đốc xuất công và lịch sử theo bộ lọc bằng CSV UTF-8 mở được bằng Excel,
  không phải file .xlsx. Nhân viên và Trưởng phòng không có quyền xuất.
- Trạng thái duyệt lưu riêng theo nhân viên/tháng; Nhân sự/Giám đốc nhấn Duyệt bảng công
  cạnh Lịch sử điều chỉnh công trên trang chi tiết. Kỳ công hoàn tất khi đủ nhân viên đã duyệt.
  Cần kiểm tra cho biết có bản ghi thiếu dữ liệu,
  không phải trạng thái phê duyệt mới. Ngày trống không tự trở thành nghỉ không phép.
- Bố cục dùng xanh đậm/vàng theo mẫu. Công chuẩn và giờ làm lấy từ dữ liệu thực tế trong ca;
  không cố định 26 công hay tính 08:00–17:00 thành 9 giờ như số minh họa trong ảnh.

## Thiết lập dữ liệu thật

1. Admin > Groups: lệnh setup_roles tạo Nhân viên, Trưởng phòng, Nhân sự, Giám đốc.
2. Admin > Users: tạo tài khoản và chọn nhóm cho từng người. Không bật staff/superuser
   cho nhân viên thường. Cổng admin chỉ dành cho superuser, kể cả staff có model permission.
3. Tạo Department chưa gán manager; tạo Employee gắn User, Department, ngày vào làm và
   lương cơ bản. Sau đó gán manager của Department tới Employee phụ trách phòng đó.
4. Admin > Attendance periods: nhập tháng/năm, các giờ làm/nghỉ và giờ/công theo chính sách
   nhóm đã xác nhận. Thời gian ngoài ca không làm tăng công hưởng lương.
5. Tạo lịch đủ tháng bằng lệnh dưới sau khi nhóm xác nhận ngày làm/ngày lễ; đây chỉ là
   ví dụ tham số, không phải lịch chính thức. Lệnh không ghi đè tháng đã có lịch.

```powershell
python manage.py create_calendar --year 2026 --month 11 --workdays 0,1,2,3,4
# Nếu có ngày lễ trong tháng: thêm --holidays 2026-11-01,2026-11-02 theo lịch thực tế.
```

6. Kiểm tra từng ngày, kể cả nghỉ/lễ, trong Admin > Work calendar days. expected_units là
   công chuẩn ngày; ngày nghỉ/lễ bằng 0. Sửa ngày nghỉ bù/làm bù nếu có. Chỉ sau khi kiểm tra
   mới bật policy_confirmed của kỳ. Số ngày công chuẩn tháng lấy từ lịch này.

   Với UC-3, sau cấu hình ban đầu, tháng mới tự kế thừa ca và lịch tuần của kỳ trước gần nhất
   đã xác nhận. Mở trang chấm công chỉ xem trước; lần check-in thành công đầu tiên mới lưu
   kỳ mới và lịch đủ tháng. Không sao chép trạng thái duyệt, không ghi đè ngày lễ/nghỉ/làm bù
   đã cấu hình ở tháng đích. HR vẫn cần khai báo các ngoại lệ lễ/nghỉ bù theo lịch thực tế;
   hệ thống không tự suy đoán ngày lễ. Nếu lịch nguồn thiếu ngày, chưa xác nhận hoặc có
   nhiều quy tắc khác nhau cho cùng thứ trong tuần, hệ thống báo cần HR xác định lịch.
   Tạo kỳ tháng mới không tự tạo dữ liệu chấm công, duyệt công hoặc tính lương.
7. Nhân sự ghi công tại /attendance/new/. Ngày thiếu dữ liệu phải đánh dấu incomplete,
   không tự coi là nghỉ không phép. Nhập nghỉ phép đã duyệt tại Admin > Leave days.
   Nghỉ nửa ngày có thể đi cùng công nửa ngày, tổng không vượt công chuẩn ngày.
8. Check-out sau 17:00 tự có OT theo giờ thực tế, không cần gửi/duyệt. Mở Bảng công hoặc chi tiết ngày để xem; sửa giờ ra sẽ tính lại OT. Giữ nguyên quy trình duyệt/khóa Bảng công.
9. Nhân sự/Giám đốc chọn tháng/năm tại /attendance/, mở chi tiết từng nhân viên và bấm
   Duyệt bảng công cạnh Lịch sử điều chỉnh công. Hệ thống kiểm tra đủ ngày của riêng người đó,
   tính lại chỉ số, lưu người/thời gian duyệt và chuyển dòng đó sang Đã duyệt. Khi đủ nhân viên
   được duyệt, kỳ công hoàn tất và có thể tính lương toàn kỳ.
10. Kỳ lương tự được tạo khi duyệt công. Nhân sự mở **Thiết lập tính lương** tại /payroll/,
    xác nhận căn cứ thuế/BH của từng nhân viên và đánh dấu đã kiểm tra.
    Nhập phụ cấp/khấu trừ có căn cứ; không nhập phạt đi muộn trùng phần công đã giảm.
11. Admin > Bonuses: nhập thưởng đúng tháng/năm; chỉ thưởng đã duyệt mới cộng vào lương.
    Không tự sinh thưởng chuyên cần/thâm niên; nhóm quản lý thưởng quyết định và duyệt.
12. Lương chưa duyệt tự cập nhật sau khi lưu đầu vào, duyệt công, duyệt thưởng hoặc đổi lương cơ bản;
    không có nút tính lương. Thiếu công/căn cứ hợp lệ thì phải bổ sung. Giám đốc kiểm tra phiếu lương,
    duyệt; sau đó Nhân sự/Giám đốc có thể xuất CSV/JSON/TXT theo bộ lọc.
13. Giám đốc chỉ xác nhận chi trả khi đã duyệt và có mã giao dịch/đường dẫn chứng từ.

## Công thức và ranh giới chính sách

- Giờ làm thường là giao giữa giờ vào/ra với khung làm việc, trừ giao với nghỉ trưa.
  Công thường không vượt 17:00 để không trùng OT. Ngày nghỉ/lễ không sinh công thường; OT tính riêng theo lịch.
- Công thực tế = giờ hợp lệ / giờ mỗi công, tối đa công chuẩn ngày; cộng công nghỉ hưởng
  lương đã duyệt, kiểm tra trùng với công thực tế. Chỉ số công/giờ lưu 4 chữ số thập phân.
- Lương theo công = lương cơ bản / công chuẩn tháng × công hưởng lương.
- Tiền OT = lương giờ thực trả do HR xác nhận × giờ OT tự động từ chấm công × hệ số theo lịch. Bản ghi OT lịch sử không tham gia nguồn mới, không cộng trùng.
- BH = tổng lương đóng BH × từng tỷ lệ trong JSON; ví dụ cú pháp {"BHXH": "0.08"}.
  Đây là ví dụ định dạng, không phải tỷ lệ mặc định. Không tham gia BH thì nhập {}, căn cứ
  miễn/không áp dụng và xác nhận. Tỷ lệ phải ở [0,1], tổng không vượt 1.
- Thuế TNCN: tự tính biểu lũy tiến 5 bậc cho cá nhân cư trú, hợp đồng từ 03 tháng,
  kỳ 07–12/2026. HR xác nhận căn cứ, giảm trừ và phân loại phụ cấp; không nhập đè số thuế.
  Dữ liệu lịch sử giữ nguyên. Xem phạm vi, công thức và nguồn luật tại [hướng dẫn thuế](docs/income-tax.md).
- Thực nhận = lương theo công + OT hợp lệ + thưởng duyệt + phụ cấp duyệt - BH - thuế - khấu trừ duyệt.
  Dùng Decimal; tính thực nhận từ giá trị trung gian chưa làm tròn, ROUND_HALF_UP tới đồng
  ở cuối. Thành phần lưu 8 số thập phân, breakdown giữ công thức/giá trị chính xác dạng chuỗi.
- Số công nghỉ là tổng nghỉ phép đã duyệt, không suy diễn ngày thiếu chấm công thành ngày nghỉ.
  Đi muộn lưu phút; chia 60 để đọc theo giờ, không tự tạo khoản phạt tiền.

## Quyền và khóa kỳ

| Vai trò | Phạm vi | Thao tác |
| --- | --- | --- |
| Nhân viên | Bản thân | Xem công/lương/nhân viên; không xuất |
| Trưởng phòng | Phòng có Department.manager là bản thân | Xem; không sửa/duyệt lương |
| Nhân sự | Toàn công ty trong bản đồ án | Sửa công kỳ mở, nhập đầu vào lương, tính, xuất kỳ duyệt |
| Giám đốc | Toàn công ty | Thao tác Nhân sự, duyệt/mở lại, xác nhận chi trả |
| Superuser | Quản trị hệ thống | Quản lý dữ liệu gốc và thao tác nghiệp vụ |

Nhân sự/Giám đốc được duyệt công từng nhân viên theo yêu cầu mới. Quyền toàn công ty
của Nhân sự và quyền chi trả của Giám đốc là thiết kế
của bản tích hợp này, cần nhóm review trước khi dùng làm chính sách chính thức.
Nếu một tài khoản có nhiều nhóm, quyền Nhân sự/Giám đốc mở phạm vi toàn công ty.

Chỉ POST có CSRF mới thay đổi trạng thái hoặc xuất file. Truy cập chi tiết lọc phạm vi
trước khi lấy bản ghi. ModelChoiceField chỉ chấp nhận nhân viên/phòng thuộc quyền.
Chỉ superuser được truy cập Admin; dữ liệu công/lương đã tính và log ở đó chỉ đọc.
Quyền này không bảo vệ trước người có quyền truy cập trực tiếp database/Django shell.

Kỳ công đã duyệt khóa sửa công, nghỉ phép, lịch và OT qua giao diện. Muốn sửa phải mở lại
kỳ lương đã duyệt (nếu có), rồi mở công, sửa, duyệt công, tính lại và duyệt lại lương.
Không mở trực tiếp kỳ đã chi trả; cần quy trình điều chỉnh riêng do nhóm xác nhận.
Thay đổi đầu vào lương làm mất hiệu lực lần tính trước và bắt buộc tính lại trước duyệt.
Lương đã duyệt/chi trả xuất từ snapshot, không đọc lại lương cơ bản/thưởng hiện tại.
Lịch sử tính cũ giữ trong PayrollAuditLog; lịch sử sửa công có trước/sau, người và lý do.
Chưa có lịch sử hợp đồng/ngày nghỉ việc theo hiệu lực: cần nhóm bổ sung nếu tính hồi tố
cho nhân viên đã ngừng làm hoặc thay lương giữa tháng.

## Kiểm thử

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Test dùng database riêng, tài khoản/nhân viên giả chỉ tồn tại trong test. Không đổ dữ liệu mẫu
vào database thật. Các test bao phủ phạm vi cá nhân/phòng, trùng công, checkout,
nghỉ hưởng/không hưởng lương, OT tự động, thưởng duyệt, điều kiện tính/duyệt/chi trả, snapshot,
CSV/JSON/TXT, CSRF và làm tròn tiền.

## GitHub và tích hợp nhóm

Xem docs/github-workflow.md. Thư mục hiện tại chưa có lịch sử .git; cần clone repository
nhóm sang thư mục riêng, tạo nhánh, rồi chép các app và migration tương ứng để review.
Không đè requirements/settings của nhóm; hợp nhất thay đổi cần thiết và dùng Django 4.2.8.
Các app employees, leaves, bonuses trong bản này là thiết kế tích hợp mới theo yêu cầu tạo
toàn bộ dự án; thành viên nhóm cần review trước khi thay thế bản app khung của họ.
Không tự push lên GitHub trong đợt này.

Biến môi trường: DJANGO_SECRET_KEY, DJANGO_DEBUG (1/0), DJANGO_ALLOWED_HOSTS (dấu phẩy).
Mặc định phục vụ phát triển local. Dùng secret riêng khi đưa lên môi trường chung.
SQLite phù hợp đồ án chạy local; chưa kiểm thử tải đồng thời nhiều người ghi và khóa kỳ
trên môi trường triển khai. Sao lưu database trước khi áp dụng migration ở máy nhóm.
