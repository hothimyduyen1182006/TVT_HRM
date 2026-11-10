> Quy định hiện hành: OT tự động cho mọi phòng ban từ chấm công; không gửi/duyệt OT. Ngày thường tính sau 17:00; xem README.md để biết ngày nghỉ/lễ, giới hạn và dữ liệu lịch sử. Các mô tả duyệt OT bên dưới chỉ là lịch sử.

# Thỏa thuận tích hợp bảng công và bảng lương

Trạng thái: bản thiết kế ban đầu để nhóm review. Các model tích hợp đã được triển khai
theo yêu cầu tiếp theo tạo toàn bộ dự án; xem README.md để biết tên trường và hành vi thực tế.
Đã xác nhận: Django 4.2.8; dùng app attendance và payroll.
Đã tạo Employee, Department, Bonus trong bản tích hợp; vẫn dùng User mặc định Django.
Khi đưa lên repository nhóm cần các thành viên review và thống nhất trước khi merge.

## Dữ liệu module khác cần cung cấp

Tên dưới đây là tên đề xuất. Khi nhóm chốt phải cập nhật tài liệu trước khi tạo migration phụ thuộc.

| Nguồn | Trường/quan hệ đề xuất | Điều kiện |
| --- | --- | --- |
| employees.Employee | code, full_name, user, department, hire_date, base_salary, is_active | code duy nhất; user OneToOne tới settings.AUTH_USER_MODEL; department ForeignKey; tiền Decimal |
| employees.Department | code, name, manager | code duy nhất; manager liên kết Employee; xác định cách xử lý phòng chưa có quản lý |
| bonuses.Bonus | employee, month, year, amount, bonus_type, status, approved_by, approved_at | Chỉ approved mới được tính; không xóa khoản đã dùng trong lương đã duyệt |
| leaves (tên model chờ chốt) | employee, start/end, loại nghỉ, mức hưởng công, status | Cần hỗ trợ nghỉ một phần ngày và ngăn cộng trùng với công thực tế |
| accounts | đăng nhập, Group, Permission, liên kết Employee | Không tạo User thứ hai; thiếu hồ sơ hoặc phạm vi thì từ chối truy cập |

Lương cơ bản có thể lấy từ hợp đồng thay vì Employee nếu nhóm thống nhất.
Phải xác định lương có hiệu lực theo kỳ; lương đóng bảo hiểm là dữ liệu riêng.
Thưởng thâm niên do bonuses cung cấp sau duyệt; payroll không tự sinh hay cộng trùng.

## Phạm vi phần bảng công

- WorkCalendarDay: ngày làm việc/nghỉ/lễ và công chuẩn theo lịch áp dụng.
- AttendancePeriod: tháng/năm, phạm vi áp dụng, trạng thái duyệt, người/thời gian duyệt.
- AttendanceRecord: employee, date, check_in/out, trạng thái, giờ hợp lệ, phút muộn,
  công thực tế, công nghỉ hưởng lương, công hưởng lương và ghi chú.
- Ràng buộc database duy nhất (employee, date); kiểm tra checkout > checkin khi có cả hai.
- OvertimeApproval: employee, ngày, giờ được duyệt, loại ngày, hệ số, thông tin duyệt.
- AttendanceAuditLog: người sửa, thời gian, lý do, trước/sau; người thường không sửa/xóa.

Chưa tự áp dụng lịch 08:00–17:00, nghỉ trưa hay hệ số OT cho đến khi nhóm chốt.
Không tự gán nghỉ không phép cho ngày thiếu chấm công. Kỳ đã duyệt phải mở lại có lý do.
Cần chốt duyệt theo phòng hay toàn công ty, và xử lý dữ liệu công đổi sau khi đã tính lương.

## Phạm vi phần bảng lương

- PayrollPeriod: tháng/năm, phạm vi, pending/approved/paid, người và thời gian chuyển trạng thái.
- PayrollRecord: employee và kỳ; duy nhất (employee, period); bản chụp mã/tên/phòng,
  lương cơ bản, công chuẩn, công hưởng lương, giờ OT, phút muộn, số công nghỉ và các thành tiền.
- PayrollComponent: chi tiết thưởng/phụ cấp/bảo hiểm/thuế/khấu trừ, nguồn và chính sách áp dụng.
- PayrollAuditLog: tính, duyệt, mở lại, chi trả; ghi lý do và bằng chứng thanh toán.
- PayrollExportLog: người, thời gian, kỳ, phạm vi hiệu lực, định dạng và các bản ghi được xuất.

Chỉ tính khi công đã duyệt và dữ liệu chính sách đầy đủ. Thiếu thuế/bảo hiểm phải báo rõ,
không tự gán 0. Mọi phép tính tiền dùng Decimal; chỉ làm tròn kết quả cuối tới đồng.
Kỳ đã duyệt bị khóa; không tự chuyển paid khi approved. Xuất chỉ approved/paid.
Dữ liệu lịch sử phải độc lập với thay đổi Employee, Bonus và chính sách hiện tại.
Khi mở lại phải bảo toàn lịch sử phiên bản; nhóm cần chốt cách xử lý kỳ đã chi trả.

## Quyền đề xuất

| Vai trò | Phạm vi | Thao tác |
| --- | --- | --- |
| Nhân viên | Bản thân qua Employee.user | Xem công/lương; không xuất tổng hợp |
| Trưởng phòng | Department.manager | Xem nhân viên phòng; không tự sửa/duyệt lương |
| Nhân sự | Phạm vi được cấp, chờ chốt | Sửa công, tính lương, xuất lương đã duyệt |
| Giám đốc | Toàn công ty | Xem, duyệt lương, xuất lương đã duyệt |

Group không thay thế kiểm tra phạm vi dữ liệu. Mọi endpoint chi tiết, sửa và xuất phải
lọc quyền ở backend trước khi áp dụng bộ lọc người dùng. Quyền duyệt công, mở lại và
xác nhận chi trả chưa chốt; không tự cấp cho bất kỳ nhóm nào.

## Những quyết định cần nhóm ghi nhận

- Lịch làm việc, nghỉ lễ, nghỉ trưa, làm một phần ngày và làm tròn công/phút muộn.
- Nghỉ phép hưởng lương, giới hạn công ngày và xử lý trùng công/nghỉ/OT.
- OT: người duyệt, giờ được duyệt, hệ số và kỳ áp dụng.
- Nguồn lương theo kỳ, phụ cấp/khấu trừ và trạng thái duyệt.
- Thưởng thâm niên: mức cố định theo bậc hay công thức khác.
- Bảo hiểm, thuế, giảm trừ: dữ liệu, chính sách, đối tượng và ngày hiệu lực.
- Phạm vi Nhân sự; người duyệt công, mở lại và xác nhận chi trả.

## Thứ tự tích hợp và kiểm thử

1. Nhóm review và chốt tên trường, quan hệ và chính sách trong tài liệu này.
2. Thành viên tạo employees/accounts, migration và dữ liệu thử do nhóm quản lý.
3. Triển khai attendance: quyền, ghi nhận, tính công, audit, duyệt và khóa kỳ.
4. Tích hợp leaves và OT; kiểm thử nghỉ phép, trùng ngày, checkout, quyền phòng/bản thân.
5. Tích hợp bonuses và chính sách lương; tạo snapshot, kiểm thử Decimal và khóa kỳ.
6. Kiểm thử CSV/JSON/TXT đúng quyền, chỉ kỳ đã duyệt; ghi log và đối chiếu snapshot.

Migration phụ thuộc phải trỏ tới migration thật của module nguồn. Không dùng migration
giả, nhân viên giả hoặc hai model thưởng để vượt qua việc thiếu module.
