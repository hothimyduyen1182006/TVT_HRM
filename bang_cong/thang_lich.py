"""Runtime view of a calendar month; this module defines no Django model or table."""
from datetime import date, time


class ThangLich:
    def __init__(self, nam, thang):
        self.nam = int(nam)
        self.thang = int(thang)
        self.pk = self.nam * 100 + self.thang

    @property
    def trang_thai(self):
        from bang_cong.models import ChotBangCong
        from nhan_vien.models import NhanVien
        employees = NhanVien.objects.filter(dang_hoat_dong=True, ngay_vao_lam__year__lte=self.nam)
        expected = set(employees.filter(ngay_vao_lam__lte=self.last_day).values_list('pk', flat=True))
        approved = set(self.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True))
        return 'approved' if expected and expected.issubset(approved) else 'pending'

    @property
    def last_day(self):
        import calendar
        from datetime import date
        return date(self.nam, self.thang, calendar.monthrange(self.nam, self.thang)[1])

    @property
    def ds_nhan_vien(self):
        return list(self.employee_approvals.values_list('tong_hop__nhan_vien_id', flat=True))

    @property
    def employee_approvals(self):
        from bang_cong.models import ChotBangCong
        return ChotBangCong.objects.filter(tong_hop__nam=self.nam, tong_hop__thang=self.thang)

    @property
    def records(self):
        from bang_luong.models import Luong
        return Luong.objects.filter(tong_hop__nam=self.nam, tong_hop__thang=self.thang)

    @property
    def status(self):
        statuses = set(self.records.values_list('trang_thai', flat=True))
        if statuses and statuses == {'paid'}:
            return 'paid'
        if statuses and statuses.issubset({'approved', 'paid'}):
            return 'approved'
        if statuses and statuses == {'submitted'}:
            return 'submitted'
        return 'pending'

    @property
    def status_label(self):
        return {
            'pending': 'Chờ HR kiểm tra',
            'submitted': 'Chờ Giám đốc ký duyệt',
            'approved': 'Đã duyệt',
            'paid': 'Đã chi trả',
        }[self.status]

    @property
    def gio_bat_dau(self):
        return time(8)

    @property
    def bat_dau_nghi_trua(self):
        return time(12)

    @property
    def ket_thuc_nghi_trua(self):
        return time(13)

    @property
    def gio_ket_thuc(self):
        return time(17)

    @property
    def gio_chuan(self):
        from decimal import Decimal
        return Decimal(8)

    def __str__(self):
        return f'{self.thang:02}/{self.nam}'

def thang_lich(nam, thang):
    return ThangLich(nam, thang)


def thang_tu_ma(ma):
    ma = int(ma)
    return ThangLich(ma // 100, ma % 100)


def cac_thang_trong_nam(nam):
    from bang_cong.models import TongHopCong
    months = set(TongHopCong.objects.filter(nam=nam).values_list('thang', flat=True))
    months.add(date.today().month if date.today().year == int(nam) else 1)
    for month in sorted(months):
        yield ThangLich(nam, month)
