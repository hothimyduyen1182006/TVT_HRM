# Thực hành công, thưởng và lương tháng 10/2026

Bộ dữ liệu dành cho thao tác thử trên website, gắn với 8 hồ sơ hiện có. Không phản ánh thanh toán thực tế. Không có chữ DEMO trong tên hay nội dung dữ liệu.

## Chuẩn bị và chạy lại

```powershell
python manage.py prepare_october_training --dry-run
python manage.py prepare_october_training
```

Cần bản OT tự động từ check-out. Không tạo nhân viên hoặc tài khoản mới; không đổi công thức, mật khẩu hay quyền. Tháng 10 phải chưa có dữ liệu trước lần chạy đầu. Lệnh sao lưu SQLite trước khi ghi; lỗi sẽ hoàn tác cả tháng. Chạy lại sau khi đã chuẩn bị sẽ giữ nguyên mọi chỉnh sửa của người dùng.

Lịch: thứ Hai–thứ Sáu, 08:00–17:00, nghỉ trưa 12:00–13:00. Tháng có 22 công chuẩn, 31 ngày lịch và 177 bản ghi chấm công. Ngày nghỉ tuần không có công thường. Không tự tạo ngày lễ giả trong tháng 10 để thử hệ số lễ.

## Các tình huống sẵn có

| Nhân viên | Chấm công và tình huống | Trạng thái công ban đầu | Thưởng ban đầu | Phiếu lương ban đầu |
|---|---|---|---|---|
| NV01 – Hồ Thị Mỹ Duyên | Đủ 22 công; ngày 23/10 để thử sửa; có lịch sử sửa giờ vào ngày 09/10 | Chờ duyệt | Nháp: tự động và hiệu quả truyền thông | Chưa tính, chờ duyệt công |
| NV02 – Đoàn Thị Trà My | Trễ 05/10 lúc 08:20, 16/10 lúc 08:45; chuyên cần bằng 0 | Đã duyệt, khóa sửa | Đã duyệt, thâm niên 150.000đ | Đã duyệt, chưa chi trả; có thể xuất riêng |
| NV03 – Lê Duy | OT 07/10 đến 19:00 (2h), 19/10 đến 18:30 (1,5h); sáng thứ Bảy 24/10 08:00–12:00 (4h, hệ số 2) | Đã duyệt, khóa sửa | Chờ duyệt, tổng 1.050.000đ | Chờ duyệt, 7,5h OT; thưởng chờ chưa được cộng |
| NV04 – Phạm Nhi | Phép năm hưởng lương 12/10 đã duyệt; đơn 30/10 còn chờ, ngày công 30/10 chưa đủ dữ liệu | Chờ xử lý | Nháp; bổ sung chuyên cần sau khi hoàn tất phép/công | Chưa tính |
| NV05 – Lê Thị Yến Nhi | Không phép 14/10; thiếu check-out 21/10; OT ngày 20/10 đến 18:00 (1h) | Chờ xử lý | Nháp, không đạt chuyên cần | Chưa tính |
| NV06 – Đặng Huy | Nghỉ không lương 15/10; về sớm 16/10 lúc 16:00; OT 08/10 đến 18:00 (1h) | Đã duyệt, khóa sửa | Nháp; có đề xuất hỗ trợ vận hành | Chờ duyệt |
| NV07 – Bùi Nam | Phép hưởng lương nửa ngày 09/10, làm 08:00–12:00; đi trễ 13/10 lúc 09:00; đơn nghỉ 23/10 bị từ chối, vẫn đi làm | Chờ duyệt | Từ chối, có lý do, thử lập lại/gửi lại | Chưa tính |
| NV08 – Lê Thị My Na | Đủ 22 công; đầu vào lương chưa được xác nhận vì lương hồ sơ 20 triệu khác hợp đồng 11,5 triệu | Chờ duyệt | Đã duyệt 650.000đ | Chưa tính, cần đối chiếu đầu vào |

Ba phiếu lương ban đầu có chủ đích: những nhân viên còn lại cần hoàn tất quy trình trên website, không phải bị thiếu dữ liệu. Kỳ công và kỳ lương đều còn mở. Chưa có phiếu đã chi trả, mã thanh toán hoặc file xuất được tạo sẵn.

Tất cả nhân viên có phụ cấp ăn trưa **450.000đ/tháng**. NV03 thêm hỗ trợ điều kiện làm việc 200.000đ; NV06 có điện thoại 200.000đ và hoàn ứng 300.000đ đã chấp thuận. Hai đề xuất của NV07 (điện thoại/hoàn ứng, mỗi khoản 200.000đ) chưa chấp thuận nên không được cộng/trừ. Không tạo khoản phạt đi trễ/về sớm; thời gian thiếu chỉ giảm công một lần.

## Trình tự thao tác trên website

1. Mở Bảng công, Bảng thưởng, Bảng lương; chọn **tháng 10, năm 2026**. Giữ bộ lọc kỳ khi đổi tài khoản.
2. Đăng nhập `hothimyduyen`: xem công cá nhân, bấm Tổng giờ tăng ca nếu có; thử truy cập dữ liệu người khác phải bị chặn. Phiếu lương ban đầu chưa có vì công chưa duyệt.
3. Đăng nhập `quanlyphongban`: chỉ xem phạm vi Sản xuất (NV02/NV03). Không có thao tác gửi/duyệt OT; không có quyền sửa công hoặc tính lương của HR.
4. Đăng nhập `quanlynhansu`: thử sửa công NV02/NV03/NV06 đã duyệt — phải bị chặn. Mở NV01 ngày 23/10, thử đổi giờ vào 08:10, nhập lý do và lưu; xem lịch sử. Nếu muốn giữ tình huống đủ công/chuyên cần ban đầu, trả giờ vào về 08:00 rồi tính thưởng lại.
5. Vào Nghỉ phép, duyệt đơn NV04 ngày 30/10. Sau đó vào công NV04 ngày 30/10, chọn **Nghỉ phép**, để trống giờ vào/ra và lưu. Việc duyệt phép tạo ngày phép, không tự thay trạng thái bản ghi chấm công chưa đủ dữ liệu.
6. Công NV05 ngày 21/10: chọn **Có mặt**, giữ giờ vào 08:00, bổ sung giờ ra 17:00 và lý do. Ngày 14/10 vẫn giữ Nghỉ không phép, không tự bổ sung công giả.
7. Bảng thưởng: thử Tính thưởng tự động, xem nháp, gửi duyệt. Có thể lập lại đề xuất NV07 bị từ chối. Đăng nhập `giamdoc` để duyệt/từ chối; từ chối phải có lý do. Nhân viên chỉ hưởng khoản đã duyệt, có đủ thông tin.
8. Đăng nhập HR: sau khi Giám đốc duyệt thưởng NV03, bấm **Tính lương** lại. Thưởng NV03 phải chuyển từ 0 lên 1.050.000đ; OT vẫn 7,5h, không cộng đôi. Bấm nhiều lần không tăng số phiếu hoặc cộng dồn số tiền; phiếu NV02 đã duyệt được giữ nguyên.
9. Vào **Đầu vào lương**, xem thuế/BH, phụ cấp và khấu trừ. Thử sửa khoản của NV06 đang chờ duyệt. Với NV08, đối chiếu hai mức lương; xác nhận lương đóng BH/căn cứ thuế và chọn đã kiểm tra. Bộ số liệu đang giả định lương đóng BH 20 triệu, không tự sửa hợp đồng 11,5 triệu.
10. Duyệt công các nhân viên còn mở: NV01, NV04, NV05, NV07, NV08. Khi đã đủ dữ liệu của cả 8 người, kỳ công tự chuyển Đã duyệt. Tính lương lại để có đủ 8 phiếu.
11. Giám đốc thử duyệt từng phiếu hoặc toàn kỳ. Nếu công, thưởng hoặc đầu vào vừa đổi, phải tính lương lại trước; không bỏ qua cảnh báo nguồn dữ liệu.
12. Xuất thử phiếu NV02 đã duyệt theo bộ lọc nhân viên. Xuất cả danh sách có phiếu chờ duyệt phải bị chặn. Khi tất cả phiếu đã duyệt, HR/Giám đốc mới xuất cả kỳ CSV/JSON/TXT.
13. Giám đốc thử xác nhận chi trả: thiếu duyệt hoặc thiếu chứng từ phải bị chặn. Chỉ bấm xác nhận với mã chứng từ thử nghiệm khi đã trình bày xong, vì trạng thái đã chi trả bị khóa và không mở lại trực tiếp. Bộ chuẩn bị không bấm bước này thay bạn.

## Các kiểm tra biên

- Check-out trước/đúng 17:00 không có OT; 17:30 là 0,5h, 18:00 là 1h. Thử trên một bản ghi chưa khóa và phục hồi giờ sau khi kiểm tra.
- Thử check-out sớm hơn check-in: từ chối. Thiếu check-out: chưa tính OT, không duyệt công khi dữ liệu chưa đầy đủ.
- OT ban đêm/qua ngày chưa được hỗ trợ tính lương; không có dữ liệu sai loại này trong bộ chuẩn bị. Không giả lập ngày lễ tháng 10. Vượt hạn mức giờ được cảnh báo, không tự cắt tiền đã làm.
- Các URL OT cũ không còn được xử lý. Không xuất hoặc chi trả phiếu chưa đủ điều kiện. Đăng xuất rồi mở URL cá nhân phải yêu cầu đăng nhập lại.

## Giả định thuế/BH của dữ liệu thực hành

BH người lao động đặt 8% BHXH + 1,5% BHYT + 1% BHTN trên lương cơ bản; không tự khẳng định đây là căn cứ hợp đồng thật. Thuế giả định cá nhân cư trú, 0 người phụ thuộc, giảm trừ bản thân 15,5 triệu/tháng, bậc đầu đến 10 triệu là 5%. Các mức này tham khảo [hướng dẫn giảm trừ cho kỳ thuế 2026](https://nief.mof.gov.vn/tin-tuc/huong-dan-quyet-toan-thue-thu-nhap-ca-nhan-doi-voi-thu-nhap-tu-tien-luong-tien-cong-11927.html) và [biểu thuế 2026](https://xaydungchinhsach.chinhphu.vn/chi-tiet-bieu-thue-thu-nhap-ca-nhan-luy-tien-tung-phan-119260327091407544.htm).

Thuế NV08 ban đầu là 152.500đ theo giả định lương cơ bản 20 triệu + thưởng duyệt 650.000đ − BH 2,1 triệu − giảm trừ 15,5 triệu; đầu vào vẫn chưa xác nhận. Các nhân viên khác dưới ngưỡng chịu thuế ngay cả khi cộng toàn bộ OT và các khoản hỗ trợ trong bộ tình huống. Hệ thống hiện nhận số thuế do HR xác định; bộ chuẩn bị chỉ điền đầu vào, không thêm công thức thuế vào website. Các thay đổi thu nhập sau đó cần HR kiểm tra lại đầu vào thuế.
