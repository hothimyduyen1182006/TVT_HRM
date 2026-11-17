import csv
import io

from django.http import HttpResponse

from .hien_thi import cac_khoan_hien_thi


CAC_COT = ['Mã nhân viên', 'Nhân viên', 'Phòng ban', 'Tháng', 'Năm',
           'Loại thưởng', 'Khoản thưởng', 'Lý do', 'Số tiền', 'Trạng thái']


def o_van_ban(gia_tri):
    gia_tri = str(gia_tri)
    return "'" + gia_tri if gia_tri.lstrip().startswith(('=', '+', '-', '@')) else gia_tri


def tao_tep_thuong(cac_bang, nam, thang):
    """Xuất mỗi khoản thưởng thành một dòng CSV."""
    cac_dong = []
    for bang in cac_bang:
        nhan_vien = bang.nguoi_dung.employee
        for khoan in cac_khoan_hien_thi(bang):
            cac_dong.append([
                nhan_vien.ma_ho_so, nhan_vien.ho_va_ten, nhan_vien.phong_ban.ten_phong_ban,
                bang.thang, bang.nam, khoan['ten'] if khoan['tu_dong'] else 'Thưởng khác',
                khoan['ten'], khoan['ly_do'], khoan['so_tien'], bang.get_trang_thai_display(),
            ])
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(CAC_COT)
    writer.writerows([o_van_ban(o) for o in dong] for dong in cac_dong)
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="bonuses-{nam}-{thang:02}.csv"'
    return response
