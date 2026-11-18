"""Tiện ích tạo đối tượng tháng dùng chung cho bảng công và bảng lương."""
import calendar  # Dùng để tìm số ngày trong một tháng.
from datetime import date, time  # Dùng kiểu ngày và giờ của Python.
from decimal import Decimal  # Dùng số thập phân chính xác cho các giá trị tính công.


class ThangLich:  # Đại diện cho một tháng trong lúc chương trình chạy, không tạo bảng database.
    """Đối tượng chứa thông tin tháng và các dữ liệu liên quan đến tháng đó."""

    def __init__(self, nam, thang):  # Khởi tạo đối tượng từ năm và tháng.
        self.nam = int(nam)  # Đảm bảo năm có kiểu số nguyên.
        self.thang = int(thang)  # Đảm bảo tháng có kiểu số nguyên.
        self.pk = self.nam * 100 + self.thang  # Tạo mã tháng dạng YYYYMM, ví dụ 202611.

    @property  # Cho phép gọi trang_thai như thuộc tính: thang.trang_thai.
    def trang_thai(self):  # Tính trạng thái duyệt công của tháng.
        from nhan_vien.models import NhanVien  # Nạp model tại đây để tránh import sớm giữa các ứng dụng.

        can_duyet = set(NhanVien.objects.filter(  # Lấy tập mã nhân viên đang làm và đã vào làm trước cuối tháng.
            dang_hoat_dong=True,  # Chỉ tính nhân viên đang hoạt động.
            ngay_vao_lam__lte=self.last_day,  # Bỏ qua nhân viên bắt đầu làm sau tháng này.
        ).values_list('pk', flat=True))  # Chỉ lấy mã nhân viên, không lấy toàn bộ đối tượng.
        da_duyet = set(  # Lấy tập mã nhân viên đã có bản chốt công trong tháng.
            self.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True)  # Lấy mã nhân viên qua bản tổng hợp.
        )
        # Chỉ trả về đã duyệt nếu có nhân viên cần duyệt và tất cả đều đã có bản chốt.
        return 'approved' if can_duyet and can_duyet.issubset(da_duyet) else 'pending'

    @property  # Cho phép gọi ngày cuối tháng như thuộc tính.
    def last_day(self):  # Tìm ngày cuối cùng của tháng này.
        so_ngay = calendar.monthrange(self.nam, self.thang)[1]  # Lấy số ngày trong tháng, có xét năm nhuận.
        return date(self.nam, self.thang, so_ngay)  # Tạo giá trị ngày cuối tháng.

    @property  # Cho phép gọi danh sách nhân viên như thuộc tính.
    def ds_nhan_vien(self):  # Lấy mã nhân viên đã có bản chốt trong tháng.
        return list(self.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True))  # Chuyển kết quả truy vấn thành danh sách.

    @property  # Cho phép truy cập các bản chốt công như thuộc tính.
    def employee_approvals(self):  # Lấy các bản chốt thuộc tháng này.
        from bang_cong.models import ChotBangCong  # Nạp model khi cần dùng để tránh import vòng.
        return ChotBangCong.objects.filter(  # Chỉ chọn bản chốt có tổng hợp đúng năm và tháng.
            tong_hop__nam=self.nam,  # Lọc theo năm của bản tổng hợp liên kết.
            tong_hop__thang=self.thang,  # Lọc theo tháng của bản tổng hợp liên kết.
        )

    @property  # Cho phép truy cập các phiếu lương tháng này như thuộc tính.
    def records(self):  # Lấy các phiếu lương có kỳ khớp với tháng này.
        from bang_luong.models import Luong  # Nạp model khi cần dùng để tránh import vòng.
        return Luong.objects.filter(  # Lọc phiếu lương qua tháng/năm ở bản tổng hợp liên kết.
            tong_hop__nam=self.nam,  # Chỉ lấy phiếu lương của năm này.
            tong_hop__thang=self.thang,  # Chỉ lấy phiếu lương của tháng này.
        )

    @property  # Cho phép gọi status như thuộc tính.
    def status(self):  # Tính trạng thái chung của các phiếu lương tháng này.
        statuses = set(self.records.values_list('trang_thai', flat=True))  # Lấy các trạng thái hiện có, không lấy toàn bộ phiếu.
        if statuses and statuses == {'Da_chi_tra'}:  # Nếu mọi phiếu đều đã chi trả...
            return 'paid'  # ...thì tháng được xem là đã chi trả.
        if statuses and statuses.issubset({'Da_duyet', 'Da_chi_tra'}):  # Nếu các phiếu đều đã duyệt hoặc đã chi...
            return 'approved'  # ...thì tháng được xem là đã duyệt.
        return 'pending'  # Chưa có phiếu hoặc còn phiếu ở trạng thái khác thì đang chờ xử lý.

    @property  # Cho phép lấy nhãn hiển thị từ trạng thái bằng thang.status_label.
    def status_label(self):  # Đổi mã trạng thái thành chữ tiếng Việt dễ đọc.
        return {
            'pending': 'Chờ duyệt',  # Nhãn cho trạng thái đang chờ.
            'approved': 'Đã duyệt',  # Nhãn cho trạng thái đã duyệt.
            'paid': 'Đã chi trả',  # Nhãn cho trạng thái đã thanh toán.
        }[self.status]  # Chọn nhãn theo trạng thái hiện tại của tháng.

    @property  # Các thuộc tính giờ bên dưới cung cấp giờ làm chuẩn của lịch.
    def gio_bat_dau(self):  # Giờ bắt đầu làm việc trong ngày.
        return time(8)  # Trả về 08:00.

    @property
    def bat_dau_nghi_trua(self):  # Giờ bắt đầu nghỉ trưa.
        return time(12)  # Trả về 12:00.

    @property
    def ket_thuc_nghi_trua(self):  # Giờ kết thúc nghỉ trưa.
        return time(13)  # Trả về 13:00.

    @property
    def gio_ket_thuc(self):  # Giờ kết thúc làm việc trong ngày.
        return time(17)  # Trả về 17:00.

    @property
    def gio_chuan(self):  # Số giờ làm việc chuẩn trong một ngày.
        return Decimal(8)  # Dùng Decimal để tính toán chính xác, trả về 8 giờ.

    def __str__(self):  # Quy định cách hiển thị đối tượng tháng thành chuỗi.
        return f'{self.thang:02}/{self.nam}'  # Hiển thị tháng 2 chữ số, ví dụ 11/2026.


def thang_lich(nam, thang):  # Tạo đối tượng tháng từ hai giá trị năm và tháng.
    return ThangLich(nam, thang)  # Dùng chung lớp ThangLich để chuẩn hóa và lưu các tiện ích tháng.


def thang_tu_ma(ma):  # Tạo đối tượng tháng từ mã dạng YYYYMM.
    ma = int(ma)  # Đảm bảo mã tháng là số nguyên để có thể chia và lấy phần dư.
    return ThangLich(ma // 100, ma % 100)  # Chia lấy năm và tháng từ mã YYYYMM.


def cac_thang_trong_nam(nam):  # Lần lượt tạo các tháng có dữ liệu trong năm được yêu cầu.
    from bang_cong.models import TongHopCong  # Nạp model tại đây để tránh import vòng.

    thang_da_co = set(  # Tạo tập tháng đã có bản tổng hợp công trong năm.
        TongHopCong.objects.filter(nam=nam).values_list('thang', flat=True)  # Chỉ đọc số tháng từ database.
    )
    hom_nay = date.today()  # Lấy ngày hiện tại.
    thang_mac_dinh = hom_nay.month if hom_nay.year == int(nam) else 1  # Dùng tháng hiện tại nếu cùng năm, nếu không thì dùng tháng 1.
    thang_da_co.add(thang_mac_dinh)  # Bảo đảm danh sách có ít nhất một tháng để hiển thị.
    for thang in sorted(thang_da_co):  # Duyệt các tháng theo thứ tự tăng dần.
        yield ThangLich(nam, thang)  # Trả từng đối tượng tháng, không tạo cả danh sách cùng lúc.
