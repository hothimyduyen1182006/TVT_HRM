import csv
import io
import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse

from bang_luong.models import Luong
from nhan_vien.access import GIAM_DOC, NHAN_SU, co_vai_tro, nhan_vien_duoc_hien_thi


def phieu_luong_ca_nhan(user):
    return Luong.objects.select_related(
        'tong_hop__nhan_vien__phong_ban', 'tong_thuong',
    ).filter(tong_hop__nhan_vien__nguoi_dung=user, tong_thuong__trang_thai='da_duyet')


def du_lieu_phieu_luong(phieu):
    cong = phieu.tong_hop
    nhan_vien = cong.nhan_vien
    return {
        'Mã nhân viên': nhan_vien.ma_ho_so,
        'Họ tên': nhan_vien.ho_va_ten,
        'Phòng ban': nhan_vien.phong_ban.ten_phong_ban,
        'Mã lương': phieu.ma_luong,
        'Lương cơ bản': phieu.luong_co_ban,
        'Công chuẩn': cong.cong_chuan,
        'Nghỉ phép có lương': cong.cong_nghi_co_luong,
        'Nghỉ không phép': cong.so_ngay_khong_phep,
        'Tổng công': cong.tong_cong,
        'Lương theo công': phieu.luong_theo_cong,
        'Giờ tăng ca': cong.tong_gio_tang_ca,
        'Lương tăng ca': phieu.luong_tang_ca,
        'Phụ cấp': phieu.phu_cap,
        'Tổng tiền thưởng': phieu.tong_tien_thuong,
        'Số phút đi trễ': cong.so_phut_tre,
        'Khấu trừ bảo hiểm (BHXH, BHYT, BHTN)': phieu.khau_tru_bhxh,
        'Thuế TNCN': phieu.thue_tncn,
        'Khấu trừ khác': phieu.khau_tru_khac,
        'Thực lĩnh': phieu.luong_thuc_linh,
        'Trạng thái': phieu.get_trang_thai_display(),
    }


def xuat_du_lieu_luong(actor, queryset, fmt, month, year, scope=None):
    if not co_vai_tro(actor, NHAN_SU, GIAM_DOC):
        raise PermissionDenied('Không có quyền xuất bảng lương.')
    phieu_luong = list(queryset.filter(
        tong_hop__thang=month, tong_hop__nam=year,
        tong_thuong__trang_thai='da_duyet',
        trang_thai__in=['Cho_giam_doc_duyet', 'Da_duyet'],
        tong_hop__nhan_vien__in=nhan_vien_duoc_hien_thi(actor),
    ).select_related('tong_hop__nhan_vien__phong_ban').order_by(
        'tong_hop__nhan_vien__ma_ho_so',
    ))
    if not phieu_luong:
        raise ValidationError('Chưa có dữ liệu lương đã duyệt để xuất.')

    rows = [du_lieu_phieu_luong(phieu) for phieu in phieu_luong]
    if fmt == 'json':
        content = json.dumps(rows, ensure_ascii=False, default=str, indent=2)
        content_type = 'application/json; charset=utf-8'
    else:
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), delimiter=',' if fmt == 'csv' else '\t',
        )
        writer.writeheader()
        writer.writerows({key: str(value) for key, value in row.items()} for row in rows)
        content = ('\ufeff' if fmt == 'csv' else '') + stream.getvalue()
        content_type = 'text/csv; charset=utf-8' if fmt == 'csv' else 'text/plain; charset=utf-8'

    LogEntry.objects.log_action(
        user_id=actor.pk,
        content_type_id=ContentType.objects.get_for_model(Luong).pk,
        object_id=f'{year}-{month:02}', object_repr=f'Bảng lương {month:02}/{year}',
        action_flag=CHANGE, change_message=f'Xuất bảng lương định dạng {fmt}.',
    )
    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="bang-luong-{year}-{month:02}.{fmt}"'
    return response
