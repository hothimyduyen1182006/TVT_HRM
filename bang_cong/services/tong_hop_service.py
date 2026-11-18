"""Tạo và đọc tổng hợp công tháng làm dữ liệu đầu vào cho bảng lương."""  # Mô tả nhiệm vụ chung của file.

from decimal import Decimal  # Dùng số thập phân chính xác khi cộng công và giờ.

from django.db import transaction  # Cho phép lưu các thay đổi database trong một giao dịch.

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong  # Các bảng chấm công, chốt công và tổng hợp công.
from bang_cong.services.cham_cong_service import (  # Dùng hàm nạp kết quả công ngày và lấy công chuẩn cố định.
    cong_chuan_thang, nap_cong_ngay,
)


def du_lieu_tong_hop(nhan_vien, nam, thang):
    """Tính các khoản công của một nhân viên trong kỳ công."""  # Hàm này tính dữ liệu, chưa lưu vào database.
    # Lấy các bản ghi chấm công của nhân viên trong tháng và sắp xếp theo ngày.
    records = list(ChamCong.objects.filter(
        nhan_vien=nhan_vien,  # Chỉ lấy dữ liệu của nhân viên đang tổng hợp.
        ngay__year=nam,  # Chỉ lấy ngày thuộc năm được yêu cầu.
        ngay__month=thang,  # Chỉ lấy ngày thuộc tháng được yêu cầu.
    ).order_by('ngay'))  # Sắp ngày từ cũ đến mới; list() thực hiện truy vấn và giữ kết quả trong danh sách.
    if records:  # Chỉ nạp/tính thêm kết quả ngày nếu thực sự có bản ghi chấm công.
        nap_cong_ngay(records, nam, thang)  # Cập nhật các kết quả công ngày từ giờ vào/ra và nghỉ phép.

    zero = Decimal('0')  # Số 0 kiểu Decimal để phép cộng công dùng cùng kiểu dữ liệu chính xác.
    cong_thuc_te = sum((record.cong_thuc_te for record in records), zero)  # Cộng số công thực tế của các ngày.
    cong_nghi = sum((record.cong_nghi_co_luong for record in records), zero)  # Cộng số công nghỉ vẫn được hưởng lương.
    cong_chuan = cong_chuan_thang(nam, thang)  # Mọi tháng đều dùng công chuẩn cố định là 24.
    gio_tang_ca = sum((record.so_gio_tang_ca for record in records), zero)  # Cộng tổng số giờ tăng ca.
    so_phut_tre = sum(record.so_phut_tre for record in records)  # Cộng tổng số phút đi trễ.
    so_ngay_vang = sum(record.trang_thai == 'absent' for record in records)  # Đếm số ngày có trạng thái nghỉ không phép.
    # Kiểm tra nhân viên này đã có bản chốt công trong đúng tháng/năm chưa.
    da_chot = ChotBangCong.objects.filter(
        tong_hop__nhan_vien=nhan_vien,  # Lọc qua bản tổng hợp có nhân viên cần kiểm tra.
        tong_hop__nam=nam,  # Lọc bản tổng hợp theo năm.
        tong_hop__thang=thang,  # Lọc bản tổng hợp theo tháng.
    ).exists()  # Chỉ cần biết có hay không, không cần tải cả bản ghi chốt.

    return {  # Trả kết quả dưới dạng từ điển, dùng tên trường của model TongHopCong.
        'thang': thang,  # Tháng được tổng hợp.
        'nam': nam,  # Năm được tổng hợp.
        'cong_chuan': cong_chuan,  # Tổng công chuẩn của tháng.
        'cong_thuc_te': cong_thuc_te,  # Tổng công nhân viên đã làm.
        'cong_nghi_co_luong': cong_nghi,  # Tổng công nghỉ có hưởng lương.
        'so_ngay_khong_phep': so_ngay_vang,  # Số ngày nghỉ không phép.
        'tong_cong': cong_thuc_te + cong_nghi,  # Tổng công tính lương gồm công làm và công nghỉ hưởng lương.
        'tong_gio_tang_ca': gio_tang_ca,  # Tổng giờ tăng ca trong tháng.
        'so_lan_tre': sum(record.so_phut_tre > 0 for record in records),  # Đếm ngày có đi trễ, mỗi ngày trễ tính một lần.
        'so_phut_tre': so_phut_tre,  # Tổng số phút đi trễ.
        'trang_thai': (  # Chọn trạng thái tổng hợp theo thứ tự ưu tiên bên dưới.
            'approved' if da_chot else  # Có bản chốt thì xem là đã duyệt.
            'incomplete' if any(record.trang_thai == 'incomplete' for record in records) else  # Thiếu dữ liệu nếu có ngày chưa đủ giờ.
            'pending' if records else 'empty'  # Có chấm công thì chờ duyệt, không có thì chưa có dữ liệu.
        ),
    }


@transaction.atomic  # Bảo đảm thao tác lưu thành công trọn vẹn hoặc được hoàn tác nếu có lỗi.
def cap_nhat_tong_hop(nhan_vien, nam, thang):
    """Lưu tổng hợp công tháng của một nhân viên."""  # Tính lại rồi tạo mới hoặc cập nhật bản tổng hợp.
    data = du_lieu_tong_hop(nhan_vien, nam, thang)  # Tạo các giá trị sẽ được lưu.
    # Tìm bản có cùng nhân viên và kỳ; nếu chưa có thì tạo bản mới.
    summary, _ = TongHopCong.objects.update_or_create(
        nhan_vien=nhan_vien,  # Điều kiện xác định nhân viên.
        nam=nam,  # Điều kiện xác định năm.
        thang=thang,  # Điều kiện xác định tháng.
        defaults=data,  # Các trường được cập nhật hoặc gán khi tạo mới.
    )
    return summary  # Trả về bản tổng hợp đã được tạo hoặc cập nhật.
