# Lịch làm việc TVT năm 2026

- Làm thứ Hai–thứ Sáu; nghỉ thứ Bảy, Chủ nhật.
- Ca mới: 08:00–17:00, nghỉ trưa 12:00–13:00, chuẩn 8 giờ/công. Các ca đã có giữ nguyên.
- Tết Dương lịch: 01/01.
- Tết Âm lịch: phương án công ty 16–20/02 (một ngày cuối năm và bốn ngày đầu năm âm lịch).
- Giỗ Tổ Hùng Vương: 26/04; nghỉ bù ngày nghỉ tuần vào 27/04.
- Ngày Chiến thắng: 30/04; Quốc tế Lao động: 01/05.
- Quốc khánh: phương án công ty 01–02/09.
- Ngày Văn hóa Việt Nam: 24/11, theo Nghị quyết 28/2026/QH16.
- Không thêm hoán đổi lịch cơ quan nhà nước vào lịch doanh nghiệp.

Ngày lễ được lưu `holiday`, công chuẩn 0. Nghỉ bù ngày nghỉ tuần được lưu `rest`, công chuẩn 0, phân biệt với hệ số làm ngày lễ. Công chuẩn tháng loại các ngày không bắt buộc làm; nhân viên đủ công của các ngày còn lại vẫn hưởng đủ lương cơ bản theo công thức hiện có. Không cộng thêm lần nữa ngày lễ vào công nghỉ phép. Không tạo đơn phép hay bản chấm công tự động cho ngày lễ.

## Cập nhật và bảo toàn dữ liệu

Quy tắc dùng chung nằm trong `bang_cong/services/cham_cong_service.py`: `lich_du_kien()` xác định loại ngày, `lich_thang()` trả lịch cả tháng. Không có model lịch hoặc kỳ tháng riêng; lịch được tính trực tiếp từ quy tắc trong code. GET chỉ xem trước; POST chấm công mới tạo dữ liệu công.

Việc gộp không ghi lại database hoặc sửa các ngày/kỳ đã có. Không tự duyệt hay chi trả lương. Lịch đã lưu được ưu tiên, gồm cả các ngoại lệ đã chốt. Lịch năm khác không lấy ngày lễ năm 2026 làm ngày lễ của năm đó.

**Ngoại lệ còn tồn tại:** 01/09/2026 đang là ngày làm việc trong kỳ đã khóa. Lệnh báo và giữ nguyên. Muốn đổi cần mở lại công/lương theo đúng quy trình và đối soát ảnh hưởng; không tự sửa dữ liệu đã duyệt.

## Nguồn

- Bộ luật Lao động, Điều 111–112: https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/9/125-vbhn-vpqh.pdf
- Phương án Tết/Quốc khánh doanh nghiệp 2026: https://baochinhphu.vn/bo-noi-vu-thong-bao-lich-nghi-tet-am-lich-va-nghi-le-quoc-khanh-nam-2026-102251017095507785.htm
- Giỗ Tổ 26/04 và nghỉ bù 27/04: https://drvn.gov.vn/thong-cao-bao-chi/thong-bao-ve-viec-nghi-le-gio-to-hung-vuong-nghi-le-giai-phong-mien-nam-va-quoc-te-lao-dong.html
- Ngày Văn hóa Việt Nam: https://xdcs.cdnchinhphu.vn/446259493575335936/2026/5/8/nq28-phat-trien-van-hoa-17782247316352069707813.pdf
