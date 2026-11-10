> Quy định hiện hành: công ty không cho phép tăng ca. Không đăng ký, duyệt hoặc tính lương OT. Các mô tả OT bên dưới chỉ phản ánh thiết kế/dữ liệu lịch sử, không áp dụng cho nghiệp vụ hiện tại.

# Giao diện Bảng lương theo vai trò

## Kế thừa và phạm vi

Template cha thực tế là templates/base.html, Navbar dùng includes/navigation.html.
payroll/base.html kế thừa cha, bổ sung CSS/JS riêng và chỉ thay nội dung block content.
Không sửa template cha, Navbar, CSS chung, model, migration hoặc công thức lương.

## Điều hướng

- /payroll/: Nhân sự, Giám đốc, superuser thấy bảng tổng hợp; Trưởng phòng thấy danh sách
  trong phòng được quản lý và không có thao tác tính/điều chỉnh/xuất.
- Nhân viên vào cùng URL thấy phiếu cá nhân, chỉ có bộ chọn tháng/năm.
- /payroll/personal/: phiếu của tài khoản đang đăng nhập; không nhận bộ lọc nhân viên khác.
- /payroll/<pk>/: dùng chung thiết kế phiếu, vẫn kiểm tra quyền theo nhân viên/phòng ở backend.
- Tính lương mở hộp thoại yêu cầu lý do rồi POST vào workflow có sẵn. Chưa có kỳ thì hướng
  dẫn tạo qua Admin, không tự tạo kỳ hoặc lương khi xem trang.
- Điều chỉnh mở trang đầu vào có sẵn, lọc theo kỳ đã chọn. Kỳ đã duyệt vẫn khóa theo service.
- Xuất mở chọn CSV/JSON/TXT, POST bộ lọc hiện tại vào service xuất có sẵn; chỉ kỳ approved/paid.

## Cập nhật: duyệt riêng phiếu từng nhân viên

Giám đốc (demo_director) và superuser có nút Duyệt bảng lương tại cột Tác vụ của từng dòng.
POST /payroll/<pk>/approve/ chỉ đổi trạng thái phiếu được chọn; lưu người/thời gian và audit.
Các vai trò khác không có nút và bị từ chối khi gọi trực tiếp endpoint. Không tự chuyển sang Đã chi trả.
Kỳ tổng hợp chuyển Đã duyệt khi tất cả phiếu trong kỳ đã duyệt; xác nhận chi trả vẫn qua
workflow có bằng chứng thanh toán. Nút duyệt toàn kỳ không còn hiển thị trong giao diện.

Trạng thái trên bảng, bộ lọc, phiếu cá nhân và file xuất lấy từ PayrollRecord.status.
Khi duyệt một phần, có thể lọc Đã duyệt để xuất các phiếu đó. Xuất có cả phiếu chờ duyệt vẫn bị từ chối.
Tính lại chỉ thay thế phiếu đang chờ duyệt; phiếu đã duyệt giữ nguyên ID, số tiền và người duyệt.
Đầu vào của nhân viên đã duyệt bị khóa; không mở lại công nếu có phiếu lương đã duyệt.
Mở lại lương có lý do qua workflow để điều chỉnh, sau đó phải tính và duyệt lại.
Migration 0003/0004 bổ sung trạng thái riêng và bảo toàn trạng thái các kỳ cũ.

Tính lương hỗ trợ kỳ công mới duyệt một phần: chỉ xử lý nhân viên có công đã duyệt,
giữ nguyên các phiếu còn chờ công và các phiếu lương đã duyệt. Khi duyệt riêng phiếu,
kiểm tra công của chính người đó và đối chiếu dữ liệu thực sự dùng tính lương.
Không bắt tính lại chỉ vì thay đổi số phiên bản, thời điểm hoặc người duyệt công.
Nếu đầu vào và số tiền vẫn khớp, cho duyệt ngay; nếu có thay đổi thì yêu cầu tính lại.

Kết quả mới lưu source_data trong breakdown (không cần migration): lương cơ bản, lịch/giờ
làm, công từng ngày, nghỉ phép, OT duyệt, thưởng duyệt, phụ cấp/khấu trừ duyệt, bảo hiểm,
thuế. Không đưa ghi chú hoặc thời gian/người duyệt vào dữ liệu so sánh. Dùng cùng hàm
payroll_values() cho việc lập phiếu và đối chiếu trong bộ nhớ, không nhân đôi công thức.
Phiếu cũ chưa có source_data được đối chiếu các thành phần/số tiền và căn cứ số đã lưu;
nếu thiếu dữ liệu đối chiếu thì thông báo cần tính lại, không mặc định cho duyệt.
Kiểm tra khi xem trang không ghi dữ liệu, không cập nhật số tiền hoặc tự duyệt.

## Dữ liệu đầu vào theo kỳ lương

/payroll/inputs/ luôn chọn tháng/năm, có lọc tên/mã, phòng ban và tình trạng thuế/BH.
Hiển thị cả nhân viên thiếu đầu vào; không tự tạo khoản thuế, bảo hiểm hoặc kỳ lương.
Hai phần riêng: Thuế và bảo hiểm (một bộ/nhân viên/kỳ), Phụ cấp và khấu trừ khác (nhiều khoản).
Các nút thêm/sửa giữ đúng kỳ và nhân viên đã chọn. Phiếu đã duyệt/chi trả chỉ được xem dữ liệu.

Tỷ lệ BH nhập bằng bảng tên loại và phần trăm, hỗ trợ thêm/loại bỏ từng dòng; không yêu cầu
người dùng nhập JSON. Dùng Decimal đổi phần trăm sang tỷ lệ thập phân, giữ schema hiện có.
Kiểm tra trùng tên, tỷ lệ âm/vượt 100%, tổng tỷ lệ và căn cứ áp dụng. Không tự điền tỷ lệ luật định.
Thuế vẫn là số đã xác định kèm căn cứ, không thay công thức hoặc tự mặc định bằng 0.
Chỉ dữ liệu đã kiểm tra và khoản cộng/trừ đã duyệt mới dùng tính lương.

save_input() khóa kỳ/phiếu ở backend, lưu trước/sau khi có thay đổi thực sự và giữ kỳ đã chọn
sau khi lưu. Lưu không đổi không thêm audit. Không dùng thao tác lưu làm lý do bắt tính lại;
điều kiện duyệt vẫn đối chiếu dữ liệu tính lương thực tế. Form cũ gửi insurance_rates vẫn được
tiếp nhận để tương thích; giao diện mới dùng formset tỷ lệ bảo hiểm.

## Điểm chưa chốt: quyền xem trước duyệt

Code trước chỉnh sửa cho nhân viên xem cả bản pending của bản thân. Ảnh mẫu lại yêu cầu
chỉ hiển thị sau duyệt. Đã báo mâu thuẫn và hỏi người dùng trước khi thay quy tắc.
Trong khi chưa có xác nhận, bản này GIỮ hành vi cũ; pending có nhãn Bản chờ duyệt và
Chưa chi trả. Thông báo trống không tuyên bố rằng phải duyệt mới được xem.
Nếu nhóm xác nhận chỉ xem sau duyệt, điều kiện phải được áp dụng đồng thời trong
employee_records(), trang cá nhân và URL chi tiết; sửa các test tương ứng.

## Dữ liệu hiển thị

- Mọi số tiền lấy từ PayrollRecord và breakdown đã lưu. Tiền có phân cách hàng nghìn;
  định dạng không ghi ngược vào database. Net dùng đúng net_pay, không tính lại từ giao diện.
- Lương cơ bản chỉ tham chiếu; tổng thu nhập không cộng lương cơ bản thêm vào lương theo công.
- Phụ cấp có trong tổng thu nhập và được thêm dòng khi có dữ liệu.
- Dữ liệu không phân loại riêng khoản phạt đi trễ. Cột/dòng phạt hiển thị “—”, không lấy tổng
  deductions làm phạt và không tự tạo công thức theo phút muộn. Các khấu trừ được duyệt
  vẫn hiển thị riêng và tính đúng vào tổng khấu trừ từ dữ liệu đã lưu.
- Cột BHXH chỉ lấy breakdown.insurance.BHXH khi nguồn khai báo đúng mã này; tổng bảo hiểm
  hiển thị kèm dưới cột và chi tiết từng loại/tỷ lệ hiện trên phiếu. Không coi tổng BH là BHXH.
- Công chuẩn/công hưởng lương/nghỉ phép/phút muộn lấy số đã lưu. Công thực tế, số ngày
  nghỉ không phép và số lần muộn lấy bảng công khi còn khớp phiên bản đã dùng tính lương;
  nếu không khớp thì hiện “—”, không suy diễn hoặc cập nhật lại bảng lương.
- Trạng thái chỉ có pending/approved/paid theo model hiện tại. Không thêm trạng thái
  Cần điều chỉnh từ ảnh vì chưa có workflow tương ứng.

## In và kiểm tra giao diện

Nút In phiếu lương gọi window.print(). CSS A4 ẩn Navbar, bộ lọc, nút và chi tiết nguồn khi
in trang lương; giữ số liệu của đúng phiếu đang xem. Quy tắc ẩn Navbar chỉ áp dụng lúc in
trang có payroll-module, không thay giao diện Navbar hoặc in module khác.

Đã dùng database test riêng để dựng 4 trạng thái và chụp đối chiếu desktop; không thêm dữ liệu
mẫu vào database dự án. Đã xuất thử PDF A4 một trang và kiểm tra bố cục trên màn hình nhỏ.

## File tạo hoặc chỉnh sửa

- payroll/views.py
- payroll/forms.py
- payroll/urls.py
- payroll/services/presentation.py
- payroll/templatetags/__init__.py
- payroll/templatetags/payroll_display.py
- payroll/static/payroll/payroll.css
- payroll/static/payroll/payroll.js
- templates/payroll/base.html
- templates/payroll/list.html
- templates/payroll/personal.html
- templates/payroll/detail.html
- templates/payroll/empty_icon.html
- payroll/tests.py
- docs/payroll-interface.md

Kiểm tra: python manage.py test và python manage.py makemigrations --check --dry-run.
