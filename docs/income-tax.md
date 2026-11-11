# Thuế TNCN tiền lương năm 2026

## Phạm vi hiện triển khai

Tạm tính theo tháng cho cá nhân cư trú có hợp đồng lao động từ 03 tháng, kỳ 07–12/2026. Đây không phải quyết toán năm. Kỳ khác, hợp đồng ngắn hạn, cá nhân không cư trú hoặc hồ sơ chưa xác định bị chặn để đối soát riêng, không mặc định thuế bằng 0.

HR vào **Bảng lương → Thiết lập tính lương → Chỉnh sửa**, chọn phương pháp thuế, xác nhận đăng ký giảm trừ bản thân tại TVT và số người phụ thuộc đủ điều kiện trong tháng. Không tự suy ra người phụ thuộc từ số con. Ghi căn cứ cư trú, hợp đồng và hồ sơ giảm trừ, rồi xác nhận đã kiểm tra. Phân loại từng phụ cấp và lưu căn cứ miễn thuế trước khi tính lương.

## Công thức

Thu nhập chịu thuế = lương theo công + thưởng đã duyệt + phụ cấp đã duyệt + tiền OT − khoản được miễn/không chịu thuế hợp lệ.

Thu nhập tính thuế = MAX(0, thu nhập chịu thuế − bảo hiểm bắt buộc người lao động đóng theo căn cứ đã xác nhận − giảm trừ bản thân − giảm trừ người phụ thuộc).

- Giảm trừ bản thân: 15.500.000 đồng/tháng nếu đăng ký tại TVT.
- Người phụ thuộc đủ điều kiện: 6.200.000 đồng/người/tháng.
- Tiền ăn giữa ca trả bằng tiền: loại trừ tối đa 1.200.000 đồng/tháng; phần vượt chịu thuế. Khoản ăn trưa 450.000 đồng cần chọn đúng phân loại, không nhận diện theo tên khoản tiền.
- OT hợp lệ đáp ứng điều kiện pháp luật: miễn toàn bộ khoản đủ điều kiện theo quy định 2026. Khi có cảnh báo vượt hạn mức, HR phải đối soát và ghi số tiền đủ điều kiện; không mặc định miễn toàn bộ. Không cắt giờ thực tế hoặc tự đổi tiền OT.
- Các phụ cấp khác mặc định chịu thuế; chỉ chọn miễn/không chịu thuế khi có hồ sơ hợp lệ. Khấu trừ tạm ứng hoặc khoản trừ thực lĩnh không tự làm giảm thu nhập tính thuế.

| Phần thu nhập tính thuế tháng | Thuế suất |
|---|---|
| Đến 10 triệu | 5% |
| Trên 10 đến 30 triệu | 10% |
| Trên 30 đến 60 triệu | 20% |
| Trên 60 đến 100 triệu | 30% |
| Trên 100 triệu | 35% |

Tính lũy tiến theo từng phần, dùng Decimal và làm tròn tổng thuế tới đồng. Ví dụ lương 20 triệu, thưởng 650.000, BH 2.100.000, ăn trưa 450.000 đủ điều kiện, không người phụ thuộc: thu nhập tính thuế 3.050.000, thuế 152.500 đồng. Hồ sơ NV08 vẫn cần đối chiếu lương hợp đồng trước khi xác nhận.

## Bảo toàn dữ liệu

Migration 0006 chỉ thêm căn cứ/phân loại thuế; đầu vào cũ được đánh dấu `legacy`, giữ nguyên số thuế và phiếu đã duyệt/chi trả. Chuyển đầu vào chưa khóa sang phương pháp tự tính và tính lại qua luồng HR. Không chỉnh phiếu đã duyệt bằng migration; cần mở lại đúng quy trình nếu muốn tính lại. Trường `tax_amount` chỉ giữ lịch sử, không nhận số thuế nhập đè trong biểu mẫu mới.

Phiếu mới lưu chi tiết tính thuế và nguồn đầu vào. Thay đổi căn cứ/thu nhập phải tính lại trước khi duyệt, xuất hoặc chi trả. Tự cập nhật tại chỗ phiếu chờ duyệt, không cộng dồn thuế.

## Căn cứ đã đối chiếu

- [Luật Thuế TNCN 109/2025/QH15 – biểu 5 bậc](https://xaydungchinhsach.chinhphu.vn/chi-tiet-bieu-thue-thu-nhap-ca-nhan-luy-tien-tung-phan-119260327091407544.htm).
- [Bộ Tài chính – giảm trừ gia cảnh kỳ thuế 2026](https://nief.mof.gov.vn/tin-tuc/huong-dan-quyet-toan-thue-thu-nhap-ca-nhan-doi-voi-thu-nhap-tu-tien-luong-tien-cong-11927.html).
- [Nghị định 253/2026/NĐ-CP, Điều 8 và Điều 26](https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/253m-ndcp.signed.pdf): tiền ăn giữa ca và thu nhập OT được miễn có điều kiện.
- [Cổng Chính phủ – tiền lương, tiền công được miễn thuế](https://baochinhphu.vn/cac-truong-hop-tien-luong-tien-cong-duoc-mien-thue-tncn-102260715163431228.htm).

HR chịu trách nhiệm xác nhận hồ sơ và căn cứ thực tế; hệ thống không thay thế việc quyết toán hoặc xử lý các chế độ chưa hỗ trợ.

## Kiểm chứng ngày 10/11/2026

- 211 kiểm thử liên quan cấu hình, nhân viên, công, lương, thưởng chạy đạt trên database thử nghiệm (gồm 11 kiểm thử thuế ban đầu).
- Bổ sung kiểm tra hiển thị trang và từ chối kỳ ngoài phạm vi; chạy lại toàn bộ 13 kiểm thử `payroll.test_tax`: đạt. Các ca bao gồm biên 5 bậc, giảm trừ, tiền ăn vượt trần, OT có cảnh báo, thưởng chịu thuế, chặn dữ liệu cũ trước chi trả/xuất và tính lại không cộng dồn.
- Trước migration đã sao lưu SQLite cục bộ; đối chiếu toàn bộ cột/bản ghi cũ của 29 bảng: không thay đổi.
- Chuyển 6 đầu vào chưa khóa của tháng 10 sang tự tính; NV02 và NV03 đã duyệt giữ nguyên toàn bộ phiếu. NV06 tính lại vẫn thuế 0đ và thực lĩnh 11.431.023đ. NV08 giữ trạng thái chưa xác nhận.
- Đối chiếu sau cập nhật: 24 bảng ngoài module lương không thay đổi. Không tạo tài khoản, không chỉnh dữ liệu công hoặc hợp đồng, không tự duyệt/chi trả lương.
- Kiểm tra trang bằng Django test client; chưa kiểm tra hiển thị trực tiếp bằng trình duyệt.
