import csv
import io
import json

from django.http import HttpResponse


CAC_COT = ['Mã nhân viên', 'Nhân viên', 'Phòng ban', 'Tháng', 'Năm',
           'Loại thưởng', 'Khoản thưởng', 'Lý do', 'Số tiền', 'Trạng thái']


def o_van_ban(gia_tri):
    gia_tri = str(gia_tri)
    return "'" + gia_tri if gia_tri.lstrip().startswith(('=', '+', '-', '@')) else gia_tri


def tao_tep_thuong(cac_dong, fmt, nam, thang):
    if fmt == 'json':
        noi_dung = json.dumps([dict(zip(CAC_COT, dong)) for dong in cac_dong],
                              ensure_ascii=False, indent=2)
        loai_tep = 'application/json'
    else:
        output = io.StringIO(newline='')
        writer = csv.writer(output, delimiter=',' if fmt == 'csv' else '\t')
        writer.writerow(CAC_COT)
        writer.writerows([o_van_ban(o) for o in dong] for dong in cac_dong)
        noi_dung = ('\ufeff' if fmt == 'csv' else '') + output.getvalue()
        loai_tep = 'text/csv' if fmt == 'csv' else 'text/plain'
    response = HttpResponse(noi_dung, content_type=loai_tep + '; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="bonuses-{nam}-{thang:02}.{fmt}"'
    return response
