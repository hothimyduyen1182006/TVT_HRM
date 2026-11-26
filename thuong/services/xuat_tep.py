import csv
import io

from django.http import HttpResponse
from django.utils.timezone import template_localtime

CAC_COT = (
    'Mã thưởng', 'Họ và tên', 'Phòng ban', 'Thưởng chuyên cần',
    'Thưởng thâm niên', 'Thưởng khác', 'Tổng thưởng', 'Trạng thái', 'Ngày duyệt',
)


def o_van_ban(gia_tri):
    gia_tri = str(gia_tri)
    return "'" + gia_tri if gia_tri.lstrip().startswith(('=', '+', '-', '@')) else gia_tri


def tao_tep_thuong(cac_bang, nam, thang):
    """Xuất mỗi bảng thưởng thành một dòng CSV."""
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(CAC_COT)
    for bang in cac_bang:
        nhan_vien = bang.nguoi_dung.employee
        ngay_duyet = ''
        if bang.ngay_duyet and bang.trang_thai in ('da_duyet', 'tu_choi'):
            ngay_duyet = template_localtime(bang.ngay_duyet).strftime('%d/%m/%Y')
        writer.writerow([
            o_van_ban(bang.ma_thuong),
            o_van_ban(nhan_vien.ho_va_ten),
            o_van_ban(nhan_vien.phong_ban.ten_phong_ban),
            bang.thuong_chuyen_can, bang.thuong_tham_nien, bang.thuong_khac,
            bang.tong_thuong, bang.get_trang_thai_display(), ngay_duyet,
        ])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    ten_tep = 'bonuses'
    if nam:
        ten_tep += f'-{nam}'
    if thang:
        ten_tep += f'-{thang:02}'
    response['Content-Disposition'] = f'attachment; filename="{ten_tep}.csv"'
    return response
