# Đối chiếu Bảng công và Bảng lương với ERD / Use Case

## Cấu trúc triển khai

| ERD | Model | Quy tắc |
|---|---|---|
| Cham_cong | ChamCong | Một nhân viên/ngày; khóa chính số nguyên `Ma_cham_cong`. |
| Tong_hop_cong | TongHopCong | Một nhân viên/kỳ và một nhân viên/tháng/năm; khóa chính `Ma_tong_hop`. |
| Chot_bang_cong | ChotBangCong | Một bản tổng hợp gắn tối đa một bản chốt; `Ma_nguoi_chot`, `Ngay_chot`; bản chốt mới tự gắn đúng tổng hợp. |
| Lich_su_dieu_chinh_cong | LichSuDieuChinhCong | Lưu bản chấm công, người sửa, trường sửa, trước/sau, lý do và thời gian. |
| Luong | Luong | Liên kết duy nhất `Ma_tong_hop`, `Ma_thuong`; kiểm tra nhân viên và kỳ công/thưởng trước khi lưu. |
| Thuong theo nhân viên/kỳ | TongThuong | Một bản tổng thưởng dùng cho lương. Bonus là từng khoản thưởng/đề xuất, không phải bản tổng thứ hai. |

Tên trường Python và ID đang dùng trong URL được giữ nguyên. `db_column` ánh xạ tên cột database sang tên trong ERD. Chuyển tên cột không thay đổi số tiền, công thức, tài khoản hoặc giao diện.

## Các khác biệt được giữ để bảo toàn chức năng

- `Luong.id` là khóa chính kỹ thuật; `Ma_luong` là mã nghiệp vụ duy nhất. Không chuyển sang khóa chính chuỗi.
- Công, tổng hợp và lương liên kết với Employee qua `Ma_nhan_vien`. Employee liên kết một-một với tài khoản Django. Không gán nhầm mã nhân viên thành mã tài khoản `Ma_nguoi_dung` trong sơ đồ.
- `TongThuong` vẫn dùng bảng `Tong_thuong`; các khoản thưởng chi tiết và quy trình đề xuất/duyệt vẫn giữ nguyên.
- Chưa tạo `Ma_phan_hoi`: sơ đồ chưa định nghĩa bảng phản hồi và website chưa có quy trình tương ứng. Nhật ký gốc được nối qua `nhat_ky`.
- Không còn model KyCong hoặc LichLamViec. PayrollPeriod quản lý trực tiếp tháng/năm, trạng thái công và trạng thái lương riêng biệt để giữ thao tác duyệt/mở lại toàn tháng. ChotBangCong và TongHopCong trỏ vào tháng dùng chung này. Lịch mới lấy từ `lich_thang()` trong `services/tinh_toan.py`.
- Căn cứ lịch sử được lưu chung trong `PayrollPeriod.can_cu_cong`, không lưu lặp trong tổng hợp công. Ca mặc định 08:00–17:00, nghỉ trưa 12:00–13:00, chuẩn 8 giờ/công; kỳ cũ giữ giờ và lịch đã áp dụng.
- Liên kết tổng hợp của bản chốt cũ vẫn cho phép NULL để tương thích dữ liệu lịch sử; mọi bản chốt mới qua `save()` đều được gắn bản tổng hợp và kiểm tra đúng nhân viên/kỳ.
- Bảng lịch sử OT đã ngừng dùng được giữ nguyên trong database; migration chỉ bỏ model khỏi trạng thái Django.

## Use Case và quyền

| Vai trò | Chức năng |
|---|---|
| Nhân viên | Check-in/check-out; xem công và lương của tài khoản mình. |
| Trưởng phòng | Xem dữ liệu trong phạm vi phòng ban theo phân quyền hiện có. |
| HR | Quản lý, chỉnh sửa, duyệt công; chuẩn bị và xuất lương. |
| Giám đốc | Duyệt lương và xác nhận chi trả. |

Kiểm tra quyền được giữ ở backend. Các thao tác duyệt/chi trả dùng POST. Công chưa duyệt thì phiếu lương cũ được giữ nhưng ẩn khỏi các trang lương; backend chặn duyệt/chi trả/xuất. Duyệt lại công sẽ cập nhật cùng phiếu, không tạo trùng. Phiếu đã duyệt/chi trả giữ quy tắc khóa hiện có.

## Migration

- attendance.0010_align_erd_columns: tên cột công, tổng hợp, chốt và lịch sử; giữ dữ liệu OT cũ.
- payroll.0009_align_erd_columns: tên cột lương; phụ thuộc migration Bảng công.
- Chỉ chạy các migration này trong đợt chỉnh sửa; không chạy migration nghỉ phép có xóa dữ liệu.

### Bỏ KyCong

- payroll.0010_unified_month_data: chuyển tháng/năm, duyệt công và căn cứ ca/lịch vào tháng lương, tạo các tháng chưa có phiếu lương mà không tạo phiếu lương.
- attendance.0012_unified_month_links: chuyển khóa ngoại tổng hợp/chốt công, sao chép căn cứ vào tổng hợp.
- payroll.0011_retire_attendance_period: bỏ khóa ngoại tới kỳ công cũ.
- attendance.0013_retire_ky_cong: bỏ model KyCong, giữ nguyên bảng gốc chỉ để lưu trữ.
- `attendance_period` trong Python là thuộc tính tương thích trả về cùng PayrollPeriod; không còn bảng kỳ công hoạt động hay quan hệ OneToOne tới KyCong.
- ID phiếu lương, chấm công và bản tổng hợp giữ nguyên. ID dùng trong đường dẫn thao tác kỳ công hiện là ID tháng dùng chung; liên kết trên giao diện được tạo theo ID mới.

Theo yêu cầu, không chạy bộ kiểm thử chức năng. Đã kiểm tra migration trên bản sao, đối chiếu toàn bộ hàng lương trước/sau, kiểm tra liên kết và khóa ngoại trước khi áp dụng database thật.

## Lịch sử sửa công và khóa sau duyệt

- Bỏ model NhatKyCong. Bảng nhật ký cũ chỉ giữ dữ liệu lưu trữ, không còn ghi mới hay xuất hiện trong Admin.
- LichSuDieuChinhCong độc lập, lưu bản chấm công, nhân viên/ngày công, người sửa, thời gian, trường, giá trị cũ/mới và lý do. Thông tin nhân viên/ngày vẫn giữ khi bản ghi chấm công cũ không còn.
- Chỉ sửa một bản chấm công đã tồn tại và có thay đổi mới ghi lịch sử; tạo mới, tính lại khi duyệt và duyệt công không ghi vào bảng này.
- Công có bản chốt là khóa vĩnh viễn, không dựa vào thời điểm cập nhật. Backend không hỗ trợ mở lại công; việc mở lại lương không mở lại công.
- Migration attendance.0014_independent_adjustment_history chuyển lịch sử sửa từ nhật ký cũ và bỏ quan hệ nhat_ky. Không xóa dữ liệu nhật ký gốc.
- Đã kiểm tra trên database sao chép: bảo toàn dữ liệu cũ, sửa có lịch sử, lưu không đổi không tạo lịch sử, duyệt không tạo lịch sử, chặn sửa sau duyệt và chặn mở lại. Không chạy toàn bộ test suite.

## Loại bỏ dữ liệu lặp (migration 0015)

- ChotBangCong chỉ lưu mã chốt, bản tổng hợp, người duyệt và ngày duyệt. Nhân viên/tháng lấy qua bản tổng hợp. OneToOne tới tổng hợp kết hợp tính duy nhất nhân viên/tháng thay cho ràng buộc lặp.
- LichSuDieuChinhCong bỏ nhan_vien/ngay_cong lưu riêng; lấy qua bản chấm công. Khóa ngoại chuyển sang PROTECT, bắt buộc tồn tại, để không mất đối tượng của lịch sử.
- TongHopCong bỏ so_gio_lam và ngay_cap_nhat không phục vụ giao diện; tổng giờ làm vẫn được tính từ ChamCong trên các trang hiện tại.
- Giữ các trường công ngày, ghi chú và căn cứ công vì đang phục vụ chức năng hiện có. Đây là các phần mở rộng ERD, không phải dữ liệu lặp có thể xóa trực tiếp.
- Migration kiểm tra mọi bản chốt và lịch sử khớp dữ liệu gốc trước khi bỏ cột; dừng nếu có liên kết thiếu hoặc không khớp. Bản sao lưu trước migration giữ dữ liệu gốc.

## Tổng công ngày và tăng ca (migration 0016)

- ChamCong.tong_cong là property bằng cong_thuc_te + cong_nghi_co_luong, làm tròn 4 chữ số. Bỏ cột tong_cong lưu lặp; tổng hợp SQL cộng trực tiếp hai thành phần. TongHopCong.tong_cong vẫn là kết quả tổng hợp tháng, giữ để tính lương.
- ChamCong.gio_tang_ca là tên đọc tương thích của so_gio_tang_ca, không tính lại trên mỗi lần truy cập. Hàm tính công vẫn cập nhật so_gio_tang_ca khi lưu/check-out; phần đối soát OT vẫn dùng cùng công thức chung.
- Migration dừng nếu tổng công cũ không khớp hai thành phần. Đã đối chiếu 416 bản ghi và kiểm tra trên bản sao: công ngày và tiền lương không đổi; các trang công/lương mở được; lưu không thay đổi không tạo lịch sử giả.

## Chấm công theo 9 cột ERD (migration 0017)

- ChamCong chỉ còn 9 trường lưu database: mã chấm công, nhân viên, ngày, giờ vào, giờ ra, số giờ làm, trạng thái, số giờ tăng ca và số phút trễ. Quan hệ nhân viên vẫn qua Employee như phương án đã thống nhất; không đổi sang auth.User trong lần này.
- Công thực tế, công nghỉ hưởng lương và tổng công ngày là giá trị tính trong service, không còn cột công ngày. Nguồn phép và lịch được nạp theo tháng để dùng lại khi tổng hợp/hiển thị.
- Bỏ cột Ghi chú và thông tin cập nhật khỏi form, bảng ngày, trang chi tiết và CSV chấm công. Lý do chỉnh sửa và người sửa vẫn nằm trong LichSuDieuChinhCong.
- Toàn bộ bản chấm công cũ (gồm ghi chú và thông tin cập nhật) được sao nguyên sang bảng lưu trữ attendance_chamcong_archive_0017 trước khi bỏ cột, không tạo model hoạt động cho bảng lưu trữ.
- Các công đã chốt giữ actual/leave trong căn cứ tháng cong_ngay_da_chot. Điều này bảo toàn các kỳ lịch sử có nguồn nghỉ phép không còn, thay vì âm thầm tính lại thành 0.
- Đối chiếu trên bản sao: 416 kết quả công ngày khớp dữ liệu cũ, bảng lương không đổi, trang công/lương/lịch sử và sửa công hoạt động. Không chạy toàn bộ bộ kiểm thử.
