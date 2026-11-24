from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

SO_NGAY_PHEP_NAM = 12

# NOTE: Tính tổng số ngày phép năm đã sử dụng trong một năm.
def tinh_ngay_phep_da_dung(nhan_vien, nam):
    dau_nam = date(nam, 1, 1)
    cuoi_nam = date(nam, 12, 31)

    cac_don = DonNghiPhep.objects.filter(
        nhan_vien=nhan_vien,
        loai_nghi='phep_nam',
        trang_thai__in=['cho_duyet', 'da_duyet'],
        ngay_bat_dau__lte=cuoi_nam,
        ngay_ket_thuc__gte=dau_nam,
    )

    tong_ngay = 0

    for don in cac_don:
        ngay_dau = max(don.ngay_bat_dau, dau_nam)
        ngay_cuoi = min(don.ngay_ket_thuc, cuoi_nam)

        tong_ngay += (ngay_cuoi - ngay_dau).days + 1

    return tong_ngay


class DonNghiPhep(models.Model):
    #Khai báo các loại nghỉ và trạng thái xử lý của đơn nghỉ phép.
    LOAI_NGHI = [
        ('phep_nam', 'Nghỉ theo quỹ phép'),
        ('luong_dac_biet', 'Nghỉ hưởng lương đặc biệt'),
        ('khong_luong', 'Nghỉ không lương'),
    ]

    CAC_TRANG_THAI = [
        ('cho_duyet', 'Đang chờ'),
        ('da_duyet', 'Đã duyệt'),
        ('tu_choi', 'Từ chối'),
        ('da_huy', 'Đã hủy'),
    ]

    ma_don = models.BigAutoField(primary_key=True)

    nhan_vien = models.ForeignKey(
        'employees.NhanVien',
        on_delete=models.PROTECT,
        related_name='don_nghi_phep',
    )

    ngay_bat_dau = models.DateField('Từ ngày')
    ngay_ket_thuc = models.DateField('Đến ngày')

    loai_nghi = models.CharField(
        'Loại nghỉ',
        max_length=20,
        choices=LOAI_NGHI,
        default='phep_nam',
    )

    ly_do = models.CharField('Lý do', max_length=255)

    #Lưu tệp minh chứng cho đơn nghỉ phép, không bắt buộc đính kèm.
    tep_dinh_kem = models.FileField(
        'Ảnh minh chứng',
        upload_to='leave_evidence/%Y/%m/',
        blank=True,
        null=True,
    )

    trang_thai = models.CharField(
        'Trạng thái',
        max_length=12,
        choices=CAC_TRANG_THAI,
        default='cho_duyet',
    )

    ghi_chu_duyet = models.TextField(
        'Lý do từ chối',
        blank=True,
    )

    ngay_tao = models.DateTimeField(auto_now_add=True)
    nguoi_duyet = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='don_nghi_phep_da_duyet',
    )

    ngay_duyet = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = 'Don_nghi_phep'
        ordering = ['-ngay_tao']

    @property
    def so_ngay_nghi(self):
        return (self.ngay_ket_thuc - self.ngay_bat_dau).days + 1

    @property
    def huong_luong(self):
        return self.loai_nghi in ('phep_nam', 'luong_dac_biet')

    def clean(self):
        loi = {}
        if self.ngay_bat_dau and self.ngay_ket_thuc:
            if self.ngay_ket_thuc < self.ngay_bat_dau:
                raise ValidationError({
                    'ngay_ket_thuc': 'Ngày kết thúc phải bằng hoặc sau ngày bắt đầu.'
                })

            #Không cho phép một nhân viên có hai đơn nghỉ trùng thời gian
            if self.nhan_vien_id and self.trang_thai in ('cho_duyet', 'da_duyet'):
                don_trung = DonNghiPhep.objects.filter(
                    nhan_vien_id=self.nhan_vien_id,
                    trang_thai__in=('cho_duyet', 'da_duyet'),
                    ngay_bat_dau__lte=self.ngay_ket_thuc,
                    ngay_ket_thuc__gte=self.ngay_bat_dau,
                ).exclude(pk=self.pk)
                if don_trung.exists():
                    loi['ngay_bat_dau'] = 'Khoảng thời gian nghỉ bị trùng với một đơn khác.'

            if self.nhan_vien_id and self.ngay_bat_dau < self.nhan_vien.ngay_vao_lam:
                loi['ngay_bat_dau'] = 'Ngày nghỉ không được trước ngày vào làm.'

            # Kiểm tra giới hạn 12 ngày phép năm cho từng năm.
            # Nếu đơn kéo dài qua nhiều năm thì kiểm tra riêng số ngày của mỗi năm.
            if (
                self._state.adding
                and self.nhan_vien_id
                and self.loai_nghi == 'phep_nam'
            ):
                for nam in range(self.ngay_bat_dau.year, self.ngay_ket_thuc.year + 1):
                    dau_nam = max(self.ngay_bat_dau, date(nam, 1, 1))
                    cuoi_nam = min(self.ngay_ket_thuc, date(nam, 12, 31))
                    so_ngay_yeu_cau = (cuoi_nam - dau_nam).days + 1
                    da_dung = tinh_ngay_phep_da_dung(self.nhan_vien, nam)

                    if da_dung + so_ngay_yeu_cau > SO_NGAY_PHEP_NAM:
                        con_lai = max(0, SO_NGAY_PHEP_NAM - da_dung)
                        loi['loai_nghi'] = f'Năm {nam} chỉ còn {con_lai} ngày phép năm.'
                        break

        if loi:
            raise ValidationError(loi)

    #Chỉ cho phép nhân viên hủy đơn khi đơn vẫn đang chờ duyệt.
    def huy(self):
        if self.trang_thai != 'cho_duyet':
            raise ValidationError('Chỉ được hủy đơn đang chờ duyệt.')

        self.trang_thai = 'da_huy'
        self.save(update_fields=['trang_thai'])

    # NOTE: Hiển thị mã đơn và tên nhân viên khi xem đối tượng trong Django Admin.
    def __str__(self):
        return f'Đơn nghỉ phép #{self.ma_don} - {self.nhan_vien}'


#Lưu từng ngày nghỉ cụ thể thuộc một đơn nghỉ phép.
#Dữ liệu này được sử dụng để theo dõi ngày nghỉ và tính công.
class NgayNghi(models.Model):
    don_nghi_phep = models.ForeignKey(
        DonNghiPhep,
        on_delete=models.PROTECT,
        related_name='cac_ngay_nghi',
    )

    ngay = models.DateField('Ngày nghỉ')

    class Meta:
        db_table = 'Ngay_nghi'
        ordering = ['-ngay']

    def __str__(self):
        return f'{self.don_nghi_phep.nhan_vien} - {self.ngay}'
