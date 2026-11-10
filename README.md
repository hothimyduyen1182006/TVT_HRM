## Phạm vi OT Phòng Sản xuất

- Áp dụng 06:00–22:00, cùng ngày; chặn ban đêm/qua ngày để không tính thiếu các khoản cộng thêm. Chưa mở trường hợp 300 giờ/năm.
- Kiểm tra tối đa 50% giờ làm bình thường trong ngày, tổng giờ làm tối đa 12; 40 giờ/tháng và 200 giờ/năm. Yêu cầu chờ duyệt giữ chỗ hạn mức. Lịch làm việc và loại ngày phải được HR kiểm tra trước.
- Giờ đề nghị được tính từ khoảng giờ, làm tròn xuống 2 chữ số thập phân; người dùng không gửi một số giờ tùy ý thay cho khoảng thực tế.
- Không cho gửi trùng/chồng lấn, gửi thay hoặc tự duyệt. Yêu cầu bị từ chối không gửi lại cùng khoảng. Mọi lần gửi/duyệt/từ chối có nhật ký.
- Quyền gửi theo phòng hiện tại; phòng ban khi gửi được lưu trên yêu cầu. Sau chuyển phòng, yêu cầu chờ của phòng cũ không được duyệt bằng quyền phòng mới; HR cần đối soát. OT đã duyệt hợp lệ không tự mất khi chuyển phòng.
- HR nhập lương giờ căn cứ OT và lý do áp dụng ở /payroll/inputs/ khi có OT đã duyệt. Không tự lấy thưởng, tiền ăn hoặc khoản hỗ trợ làm căn cứ.
- Các phòng khác vẫn giữ check-out thực tế. Hồ sơ làm thêm được công ty yêu cầu/chấp nhận ngoài Sản xuất cần HR đối soát theo quy trình ngoại lệ riêng; không được sửa giờ về cuối ca hoặc tự gộp khoản này thành OT Sản xuất.
- Không tự chuyển OT cũ thành yêu cầu mới, không tự tính lại/duyệt/chi trả phiếu lương lịch sử.
- Ba migration mới bổ sung cấu hình phòng, khoảng OT và căn cứ lương giờ. Sao lưu trước khi migrate; không xóa migration cũ.
- Căn cứ tham khảo: Điều 98, 106, 107 Bộ luật Lao động (bản hợp nhất 18/VBHN-VPQH năm 2026); Điều 55 Nghị định 145/2020/NĐ-CP. Phạm vi hiện tại không thay thế quy trình riêng cho lao động đặc thù hoặc làm thêm ban đêm.

# TVT HRM — Django 4.2.8

Bản tích hợp đồ án: nhân viên/phòng ban/tài khoản dùng Django Admin; bảng công và
bảng lương có giao diện Bootstrap, phân quyền backend, service, migration và kiểm thử.
Chỉ Phòng Sản xuất được đăng ký OT theo cấu hình Department.allows_overtime trong database. Nhân viên tự gửi; Trưởng phòng Sản xuất duyệt/từ chối; HR tổng hợp và nhập căn cứ lương giờ.
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
7. Nhân sự ghi công tại /attendance/new/. Ngày thiếu dữ liệu phải đánh dấu incomplete,
   không tự coi là nghỉ không phép. Nhập nghỉ phép đã duyệt tại Admin > Leave days.
   Nghỉ nửa ngày có thể đi cùng công nửa ngày, tổng không vượt công chuẩn ngày.
8. Quản trị bật allows_overtime cho đúng Phòng Sản xuất (database chỉ cho một phòng được bật). Check-out muộn giữ giờ thực tế, công thường chỉ tính trong ca; không tự gửi yêu cầu OT.
   Nhân viên mở chi tiết ngày công, chọn khoảng OT và lý do, xác nhận gửi. Trưởng phòng xử lý trước khi HR khóa công. URL duyệt cũ theo ID chấm công vẫn bị chặn để tránh nhầm yêu cầu.
9. Nhân sự/Giám đốc chọn tháng/năm tại /attendance/, mở chi tiết từng nhân viên và bấm
   Duyệt bảng công cạnh Lịch sử điều chỉnh công. Hệ thống kiểm tra đủ ngày của riêng người đó,
   tính lại chỉ số, lưu người/thời gian duyệt và chuyển dòng đó sang Đã duyệt. Khi đủ nhân viên
   được duyệt, kỳ công hoàn tất và có thể tính lương toàn kỳ.
10. Admin > Payroll periods: tạo kỳ lương liên kết kỳ công. Nhân sự nhập riêng dữ liệu
    thuế/BH cho từng nhân viên tại /payroll/inputs/, gồm căn cứ và đánh dấu đã kiểm tra.
    Nhập phụ cấp/khấu trừ có căn cứ; không nhập phạt đi muộn trùng phần công đã giảm.
11. Admin > Bonuses: nhập thưởng đúng tháng/năm; chỉ thưởng đã duyệt mới cộng vào lương.
    Không tự sinh thưởng chuyên cần/thâm niên; nhóm quản lý thưởng quyết định và duyệt.
12. Nhân sự chọn kỳ tại /payroll/, ghi lý do rồi tính lương. Giám đốc kiểm tra phiếu lương,
    duyệt; sau đó Nhân sự/Giám đốc có thể xuất CSV/JSON/TXT theo bộ lọc.
13. Giám đốc chỉ xác nhận chi trả khi đã duyệt và có mã giao dịch/đường dẫn chứng từ.

## Công thức và ranh giới chính sách

- Giờ làm thường là giao giữa giờ vào/ra với khung làm việc, trừ giao với nghỉ trưa.
  Ngày nghỉ/lễ không sinh công thường; OT hợp lệ của Sản xuất được tính riêng theo loại ngày.
- Công thực tế = giờ hợp lệ / giờ mỗi công, tối đa công chuẩn ngày; cộng công nghỉ hưởng
  lương đã duyệt, kiểm tra trùng với công thực tế. Chỉ số công/giờ lưu 4 chữ số thập phân.
- Lương theo công = lương cơ bản / công chuẩn tháng × công hưởng lương.
- Tiền OT = lương giờ thực trả do HR xác nhận × giờ được duyệt × hệ số theo lịch (1,5 ngày thường; 2 nghỉ tuần; 3 lễ). Chỉ yêu cầu đã gửi và duyệt hợp lệ tham gia tính; dữ liệu OT legacy không tự trở thành nguồn mới.
- BH = tổng lương đóng BH × từng tỷ lệ trong JSON; ví dụ cú pháp {"BHXH": "0.08"}.
  Đây là ví dụ định dạng, không phải tỷ lệ mặc định. Không tham gia BH thì nhập {}, căn cứ
  miễn/không áp dụng và xác nhận. Tỷ lệ phải ở [0,1], tổng không vượt 1.
- Thuế: bản hiện tại nhận số thuế đã xác định và căn cứ chính sách, thu nhập tính thuế,
  giảm trừ/người phụ thuộc từ người có trách nhiệm. Chưa tự tính biểu thuế lũy tiến vì nhóm
  chưa thống nhất quy tắc và dữ liệu. Nhập 0 chỉ khi có căn cứ; thiếu đầu vào thì chặn tính.
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
nghỉ hưởng/không hưởng lương, chặn OT, thưởng duyệt, điều kiện tính/duyệt/chi trả, snapshot,
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
