import calendar
import csv
import io
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from bang_cong.models import ChamCong
from bang_cong.services.cham_cong_service import ket_qua_cong_ngay, lich_thang
from bang_cong.utils.date_utils import thang_lich
from nghi_phep.models import NgayNghi
from nhan_vien.access import GIAM_DOC, NHAN_SU, TRUONG_PHONG, co_vai_tro, nhan_vien_duoc_hien_thi
from nhan_vien.models import NhanVien
from .forms import BonusFilter, BonusProposalForm, PersonalBonusFilter
from .models import DeXuatThuong, Thuong
from django.db import connection
from django.utils.dateparse import parse_datetime


def tinh_thuong_tham_nien(nhan_vien, thang, nam):
    ngay_ket_thuc_ky = date(nam, thang, calendar.monthrange(nam, thang)[1])
    so_nam_da_lam = ngay_ket_thuc_ky.year - nhan_vien.ngay_vao_lam.year
    chua_den_ngay_ky_niem = (ngay_ket_thuc_ky.month, ngay_ket_thuc_ky.day) < (
        nhan_vien.ngay_vao_lam.month, nhan_vien.ngay_vao_lam.day
    )
    so_nam_tham_nien = max(0, so_nam_da_lam - chua_den_ngay_ky_niem)

    if so_nam_tham_nien < 1:
        muc_thuong = Decimal(0)
    elif so_nam_tham_nien < 3:
        muc_thuong = Decimal(150000)
    elif so_nam_tham_nien < 5:
        muc_thuong = Decimal(200000)
    else:
        muc_thuong = Decimal(500000)

    so_tien = so_nam_tham_nien * muc_thuong
    ly_do = f'{so_nam_tham_nien} năm thâm niên; mức thưởng tháng áp dụng {muc_thuong:,.0f} VNĐ.'
    return 'seniority', 'Thưởng thâm niên', so_tien, ly_do


def tinh_thuong_chuyen_can(nhan_vien, thang, nam):
    ngay_bat_dau = date(nam, thang, 1)
    ngay_ket_thuc = date(nam, thang, calendar.monthrange(nam, thang)[1])
    ky_cong = thang_lich(nam, thang)
    if not ky_cong:
        raise ValidationError('Thiếu dữ liệu chấm công hoặc lịch làm việc của kỳ thưởng.')

    cong_da_duyet = (
        ky_cong.trang_thai == 'approved' and nhan_vien.pk in ky_cong.ds_nhan_vien
    ) or ky_cong.employee_approvals.filter(tong_hop__nhan_vien_id=nhan_vien.pk).exists()
    if not cong_da_duyet:
        raise ValidationError(f'Bảng công của {nhan_vien} chưa được duyệt.')

    ngay_lam_viec = [
        lich for lich in lich_thang(nam, thang, ky_cong).values()
        if max(ngay_bat_dau, nhan_vien.ngay_vao_lam) <= lich.ngay <= ngay_ket_thuc
        and lich.loai_ngay == 'work' and lich.cong_chuan > 0
    ]
    if not ngay_lam_viec:
        raise ValidationError('Thiếu dữ liệu chấm công hoặc lịch làm việc của kỳ thưởng.')

    records = {
        ban_ghi.ngay: ban_ghi
        for ban_ghi in ChamCong.objects.filter(
            nhan_vien=nhan_vien, ngay__range=(ngay_bat_dau, ngay_ket_thuc)
        )
    }
    ngay_nghi_phep = set(NgayNghi.objects.filter(
        don_nghi_phep__nhan_vien=nhan_vien,
        don_nghi_phep__trang_thai='da_duyet',
        ngay__range=(ngay_bat_dau, ngay_ket_thuc),
    ).values_list('ngay', flat=True))
    if any(ngay.ngay not in records and ngay.ngay not in ngay_nghi_phep for ngay in ngay_lam_viec):
        raise ValidationError(f'Thiếu dữ liệu chấm công của {nhan_vien}.')

    ban_ghi_ngay = [records[ngay.ngay] for ngay in ngay_lam_viec if ngay.ngay in records]
    co_ngay_nghi = any(
        lich.ngay in ngay_nghi_phep
        or (lich.ngay in records and records[lich.ngay].trang_thai in {'absent', 'leave'})
        for lich in ngay_lam_viec
    )
    if co_ngay_nghi:
        so_tien_thuong = Decimal(0)
        ly_do_thuong = 'Không đạt thưởng chuyên cần do có ngày nghỉ phép hoặc nghỉ không phép.'
    elif any(ban_ghi.trang_thai == 'incomplete' for ban_ghi in ban_ghi_ngay):
        raise ValidationError(f'Dữ liệu chấm công của {nhan_vien} chưa đầy đủ.')
    elif any(ket_qua_cong_ngay(records[lich.ngay], ky_cong, lich, False)['actual'] < lich.cong_chuan
             for lich in ngay_lam_viec):
        so_tien_thuong = Decimal(0)
        ly_do_thuong = 'Không đạt thưởng chuyên cần do chưa đủ ngày công quy định.'
    else:
        so_tien_thuong = Decimal(200000)
        ly_do_thuong = 'Đủ ngày công quy định, không có ngày vắng mặt.'
    return 'attendance', 'Thưởng chuyên cần', so_tien_thuong, ly_do_thuong


def tinh_thuong_tu_dong(nhan_vien, thang, nam):
    cac_khoan = [tinh_thuong_tham_nien(nhan_vien, thang, nam)]
    try:
        cac_khoan.append(tinh_thuong_chuyen_can(nhan_vien, thang, nam))
    except ValidationError as exc:
        return cac_khoan, exc
    return cac_khoan, None


@transaction.atomic
def dong_bo_thuong_tu_dong(nhan_vien, thang, nam):
    NhanVien.objects.select_for_update().get(pk=nhan_vien.pk)
    bang, _ = Thuong.objects.select_for_update().get_or_create(nguoi_dung=nhan_vien.nguoi_dung, thang=thang, nam=nam)
    if bang.trang_thai in ['pending', 'approved']:
        return bang
    cac_khoan, loi = tinh_thuong_tu_dong(nhan_vien, thang, nam)
    gia_tri = {'seniority': ('thuong_tham_nien', 'ly_do_tham_nien'),
               'attendance': ('thuong_chuyen_can', 'ly_do_chuyen_can')}
    thay_doi = False
    for loai, _, tien, ly_do in cac_khoan:
        cot_tien, cot_ly_do = gia_tri[loai]
        if getattr(bang, cot_tien) != tien or getattr(bang, cot_ly_do) != ly_do:
            setattr(bang, cot_tien, tien)
            setattr(bang, cot_ly_do, ly_do)
            thay_doi = True
    if loi and bang.ly_do_chuyen_can is not None:
        bang.thuong_chuyen_can, bang.ly_do_chuyen_can = Decimal(0), None
        thay_doi = True
    if thay_doi:
        luu_bang_thuong(bang)
    return bang


def luu_bang_thuong(bang):
    bang.tong_thuong = bang.thuong_chuyen_can + bang.thuong_tham_nien + bang.thuong_khac
    bang.full_clean()
    bang.save()


def gui_duyet_bang(bang):
    if bang.trang_thai not in ['draft', 'rejected'] or not bang.ly_do_chuyen_can or not bang.ly_do_tham_nien:
        raise ValidationError('Chỉ gửi bảng thưởng khi có đủ căn cứ thâm niên và chuyên cần.')
    bang.trang_thai = 'pending'
    bang.nguoi_duyet = bang.ngay_duyet = None
    bang.ly_do_tu_choi = ''
    luu_bang_thuong(bang)


def duyet_bang(bang, nguoi_dung, tu_choi=False, ly_do=''):
    if bang.trang_thai != 'pending':
        raise ValidationError('Chỉ xử lý bảng thưởng đang Chờ duyệt.')
    bang.trang_thai = 'rejected' if tu_choi else 'approved'
    bang.nguoi_duyet, bang.ngay_duyet = nguoi_dung, timezone.now()
    bang.ly_do_tu_choi = ly_do.strip() if tu_choi else ''
    luu_bang_thuong(bang)


def cap_nhat_thuong_khac(bang):
    bang.thuong_khac = bang.de_xuat.aggregate(tong=Sum('so_tien'))['tong'] or Decimal(0)
    bang.trang_thai, bang.ly_do_tu_choi = 'draft', ''
    bang.nguoi_duyet = bang.ngay_duyet = None
    luu_bang_thuong(bang)


@transaction.atomic
def luu_de_xuat(de_xuat):
    bang = Thuong.objects.select_for_update().get(pk=de_xuat.bang_thuong_id)
    if bang.trang_thai not in ['draft', 'rejected']:
        raise ValidationError('Chỉ sửa đề xuất khi bảng thưởng là Bản nháp hoặc Từ chối.')
    de_xuat.full_clean()
    de_xuat.save()
    cap_nhat_thuong_khac(bang)


@transaction.atomic
def xoa_de_xuat(de_xuat):
    bang = Thuong.objects.select_for_update().get(pk=de_xuat.bang_thuong_id)
    if bang.trang_thai not in ['draft', 'rejected']:
        raise ValidationError('Chỉ xóa đề xuất khi bảng thưởng là Bản nháp hoặc Từ chối.')
    de_xuat.delete()
    cap_nhat_thuong_khac(bang)


def nguon_thuong_truoc_chuyen_doi(bang):
    """Chỉ đọc dữ liệu lưu trữ để giữ nguyên mã nguồn của phiếu lương cũ."""
    with connection.cursor() as cursor:
        cursor.execute('SELECT id, loai_thuong, ten, so_tien, thoi_gian_de_xuat '
                       'FROM Khoan_thuong_luu_tru WHERE nhan_vien_id=%s AND nam=%s AND thang=%s',
                       [bang.nguoi_dung.employee.pk, bang.nam, bang.thang])
        return [{'id': ma, 'ma_moi': ('D' + str(ma).zfill(24) if loai == 'other' else f'{bang.pk}:{loai}'),
                 'name': ten, 'amount': format(Decimal(str(tien)), '.2f'),
                 'ngay': parse_datetime(ngay) if isinstance(ngay, str) else ngay}
                for ma, loai, ten, tien, ngay in cursor.fetchall()]


def gan_ma_hien_thi(cac_bang):
    """Giữ mã MT cũ trên giao diện, không đổi khóa liên kết với lương."""
    for bang in cac_bang:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM Khoan_thuong_luu_tru "
                "WHERE nhan_vien_id=%s AND nam=%s AND thang=%s "
                "ORDER BY CASE loai_thuong WHEN 'seniority' THEN 0 "
                "WHEN 'attendance' THEN 1 ELSE 2 END, ten, id LIMIT 1",
                [bang.nguoi_dung.employee.pk, bang.nam, bang.thang])
            cu = cursor.fetchone()
        bang.ma_hien_thi = (f'MT_{cu[0]:03d}' if cu else
                            f'MT_{bang.nam}{bang.thang:02d}_{bang.nguoi_dung_id}')
    return cac_bang


def cac_khoan_hien_thi(bang):
    ket_qua = []
    nguon_cu = nguon_thuong_truoc_chuyen_doi(bang)
    for loai, ten, tien, ly_do in [
        ('seniority', 'Thưởng thâm niên', bang.thuong_tham_nien, bang.ly_do_tham_nien),
        ('attendance', 'Thưởng chuyên cần', bang.thuong_chuyen_can, bang.ly_do_chuyen_can),
    ]:
        if ly_do is not None:
            ma = f'{bang.pk}:{loai}'
            ngay = next((r['ngay'] for r in nguon_cu if r['ma_moi'] == ma), None)
            ket_qua.append({'id': ma, 'ten': ten, 'nhan_de_loai': ten, 'so_tien': tien,
                           'ly_do': ly_do, 'tu_dong': True, 'thoi_gian_de_xuat': ngay})
    for de_xuat in bang.de_xuat.order_by('ten', 'pk'):
        ket_qua.append({'id': de_xuat.pk, 'ten': de_xuat.ten, 'nhan_de_loai': de_xuat.ten,
                       'so_tien': de_xuat.so_tien, 'ly_do': de_xuat.ly_do, 'tu_dong': False,
                       'thoi_gian_de_xuat': de_xuat.thoi_gian_de_xuat})
    return ket_qua


def cac_khoan_thuong_tinh_luong(nhan_vien_id, nam, thang):
    bang = Thuong.objects.select_related('nguoi_dung__employee').filter(
        nguoi_dung__employee__pk=nhan_vien_id, nam=nam, thang=thang).first()
    if not bang or bang.trang_thai != 'approved':
        return []
    bang.full_clean()
    cu = nguon_thuong_truoc_chuyen_doi(bang)
    ket_qua = []
    for khoan in cac_khoan_hien_thi(bang):
        nguon = [r for r in cu if r['ma_moi'] == khoan['id']]
        if nguon and sum((Decimal(r['amount']) for r in nguon), Decimal(0)) == khoan['so_tien']:
            ket_qua.extend({'id': r['id'], 'name': r['name'], 'amount': r['amount']} for r in nguon)
        else:
            ket_qua.append({'id': nguon[0]['id'] if len(nguon) == 1 else khoan['id'],
                           'name': khoan['ten'], 'amount': format(khoan['so_tien'], '.2f')})
    return ket_qua


def trang_tu_choi_truy_cap(request):
    return render(request, 'thuong/access_denied.html', status=403)


def bang_thuong_trong_pham_vi(nguoi_dung):
    return Thuong.objects.select_related('nguoi_dung__employee__phong_ban', 'nguoi_duyet').filter(
        nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung))


def loc_bang_thuong(cac_bang, du_lieu):
    for cot in ['thang', 'nam', 'trang_thai']:
        if du_lieu.get(cot):
            cac_bang = cac_bang.filter(**{cot: du_lieu[cot]})
    if du_lieu.get('nhan_vien'):
        cac_bang = cac_bang.filter(nguoi_dung__employee=du_lieu['nhan_vien'])
    if du_lieu.get('phong_ban'):
        cac_bang = cac_bang.filter(nguoi_dung__employee__phong_ban=du_lieu['phong_ban'])
    if du_lieu.get('tu_khoa'):
        cac_bang = cac_bang.filter(Q(nguoi_dung__employee__ho_va_ten__icontains=du_lieu['tu_khoa'])
                                  | Q(nguoi_dung__employee__ma_ho_so__icontains=du_lieu['tu_khoa']))
    return cac_bang


@login_required
def danh_sach_thuong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        return danh_sach_thuong_ca_nhan(request)
    du_lieu = request.GET.copy()
    if co_vai_tro(request.user, GIAM_DOC) and 'trang_thai' not in du_lieu:
        du_lieu['trang_thai'] = 'pending'
    form = BonusFilter(request.user, du_lieu, default_current_period=True)
    if not form.is_valid() and {'nhan_vien', 'phong_ban'} & set(form.errors):
        return trang_tu_choi_truy_cap(request)
    ky = form.cleaned_data if form.is_valid() else {}
    if ky.get('thang') and ky.get('nam') and co_vai_tro(request.user, NHAN_SU):
        for nhan_vien in form.pham_vi_nhan_vien(request.user):
            dong_bo_thuong_tu_dong(nhan_vien, ky['thang'], ky['nam'])
    cac_bang = loc_bang_thuong(bang_thuong_trong_pham_vi(request.user), ky) if form.is_valid() else Thuong.objects.none()
    if co_vai_tro(request.user, GIAM_DOC):
        cac_bang = cac_bang.exclude(trang_thai='draft')
    tong = cac_bang.aggregate(tong=Sum('tong_thuong'))['tong'] or Decimal(0)
    trang = Paginator(cac_bang, 5).get_page(request.GET.get('page'))
    tham_so = request.GET.copy()
    tham_so.pop('page', None)
    co_ky = bool(ky.get('thang') and ky.get('nam'))
    return render(request, 'thuong/list_redesign.html', {
        'form': form, 'rows': gan_ma_hien_thi(trang.object_list), 'page_obj': trang, 'page_query': tham_so.urlencode(),
        'tong_tien': tong, 'can_propose': co_vai_tro(request.user, NHAN_SU, TRUONG_PHONG),
        'can_send_period': co_ky and co_vai_tro(request.user, NHAN_SU) and not co_vai_tro(request.user, GIAM_DOC)
                           and bang_thuong_trong_pham_vi(request.user).filter(thang=ky['thang'], nam=ky['nam'], trang_thai__in=['draft', 'rejected']).exists(),
        'can_decide_period': co_ky and co_vai_tro(request.user, GIAM_DOC),
        'selected_thang': ky.get('thang'), 'selected_nam': ky.get('nam'),
        'can_export': co_vai_tro(request.user, NHAN_SU, GIAM_DOC),
    })


@login_required
def danh_sach_thuong_ca_nhan(request):
    nhan_vien = NhanVien.objects.filter(nguoi_dung=request.user).first()
    if nhan_vien is None and not co_vai_tro(request.user, NHAN_SU, GIAM_DOC, TRUONG_PHONG):
        return trang_tu_choi_truy_cap(request)
    form = PersonalBonusFilter(request.GET)
    tat_ca = Thuong.objects.select_related('nguoi_dung__employee__phong_ban').filter(nguoi_dung=request.user)
    ky = form.cleaned_data if form.is_valid() else {}
    cac_bang = loc_bang_thuong(tat_ca, ky).order_by('-nam', '-thang')
    da_duyet = tat_ca.filter(trang_thai='approved')
    if ky.get('nam'):
        da_duyet = da_duyet.filter(nam=ky['nam'])
    cao_nhat = da_duyet.order_by('-tong_thuong', '-nam', '-thang').first()
    gan_nhat = da_duyet.filter(thang=ky['thang']) if ky.get('thang') else da_duyet
    gan_nhat = gan_nhat.order_by('-nam', '-thang').first()
    url = reverse('thuong:personal')
    def duong_dan(bang):
        return f'{url}?thang={bang.thang}&nam={bang.nam}&trang_thai=approved' if bang else url
    nam = ky.get('nam')
    return render(request, 'thuong/personal.html', {
        'form': form, 'rows': gan_ma_hien_thi(cac_bang), 'nhan_vien': nhan_vien,
        'tong_tien': cac_bang.aggregate(tong=Sum('tong_thuong'))['tong'] or 0,
        'tong_da_nhan': da_duyet.aggregate(tong=Sum('tong_thuong'))['tong'] or 0,
        'nhan_de_tong_da_nhan': f'Tổng đã nhận (Năm {nam})' if nam else 'Tổng đã nhận (Tất cả năm)',
        'url_loc_da_nhan': f'{url}?thang=&nam={nam or ""}&trang_thai=approved',
        'tong_thang_cao_nhat': cao_nhat.tong_thuong if cao_nhat else 0, 'url_thang_cao_nhat': duong_dan(cao_nhat),
        'tong_thang_moi_nhat': gan_nhat.tong_thuong if gan_nhat else 0, 'url_ky_moi_nhat': duong_dan(gan_nhat),
    })


@login_required
def chi_tiet_thuong(request, nhan_vien_id, nam, thang):
    if NhanVien.objects.filter(pk=nhan_vien_id).exists() and not nhan_vien_duoc_hien_thi(request.user).filter(pk=nhan_vien_id).exists():
        return trang_tu_choi_truy_cap(request)
    bang = get_object_or_404(bang_thuong_trong_pham_vi(request.user), nguoi_dung__employee__pk=nhan_vien_id, nam=nam, thang=thang)
    if bang.nguoi_dung.employee.nguoi_dung_id != request.user.pk and co_vai_tro(request.user, GIAM_DOC) and not co_vai_tro(request.user, NHAN_SU) and bang.trang_thai == 'draft':
        return trang_tu_choi_truy_cap(request)
    cac_khoan = cac_khoan_hien_thi(bang)
    for khoan in cac_khoan:
        khoan['co_the_sua'] = khoan['co_the_xoa'] = (
            not khoan['tu_dong'] and co_vai_tro(request.user, NHAN_SU) and bang.trang_thai in ['draft', 'rejected'])
    return render(request, 'thuong/detail.html', {'row': bang, 'cac_khoan': cac_khoan})


def lich_su_de_xuat(nguoi_dung):
    return DeXuatThuong.objects.select_related('bang_thuong__nguoi_dung__employee__phong_ban').filter(
        bang_thuong__nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung), nguoi_de_xuat=nguoi_dung
    ).order_by('-thoi_gian_de_xuat', '-pk')


@login_required
def de_xuat_thuong_khac(request):
    if not co_vai_tro(request.user, NHAN_SU, TRUONG_PHONG):
        return trang_tu_choi_truy_cap(request)
    form = BonusProposalForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        du_lieu = form.cleaned_data
        try:
            with transaction.atomic():
                bang, _ = Thuong.objects.get_or_create(nguoi_dung=du_lieu['nhan_vien'].nguoi_dung, thang=du_lieu['thang'], nam=du_lieu['nam'])
                de_xuat = bang.de_xuat.filter(ten=du_lieu['ten']).first() or DeXuatThuong(bang_thuong=bang)
                for cot in ['ten', 'so_tien', 'ly_do']:
                    setattr(de_xuat, cot, du_lieu[cot])
                de_xuat.nguoi_de_xuat = request.user
                de_xuat.thoi_gian_de_xuat = timezone.now()
                luu_de_xuat(de_xuat)
        except ValidationError as loi:
            form.add_error(None, loi)
        else:
            messages.success(request, 'Đã thêm đề xuất thưởng khác vào Bản nháp.')
            if co_vai_tro(request.user, NHAN_SU):
                return redirect(f"{reverse('thuong:list')}?thang={bang.thang}&nam={bang.nam}")
            return redirect('thuong:detail', bang.nguoi_dung.employee.pk, bang.nam, bang.thang)
    return render(request, 'thuong/propose.html', {'form': form, 'history': lich_su_de_xuat(request.user)})


@login_required
def sua_de_xuat_thuong(request, bonus_id):
    if not co_vai_tro(request.user, NHAN_SU):
        return trang_tu_choi_truy_cap(request)
    de_xuat = get_object_or_404(lich_su_de_xuat_trong_pham_vi(request.user), pk=bonus_id)
    bang = de_xuat.bang_thuong
    form = BonusProposalForm(request.user, request.POST or None, initial={
        'thang': bang.thang, 'nam': bang.nam, 'nhan_vien': bang.nguoi_dung.employee.pk,
        'ten': de_xuat.ten, 'so_tien': de_xuat.so_tien, 'ly_do': de_xuat.ly_do})
    for cot in ['thang', 'nam', 'nhan_vien']:
        form.fields[cot].disabled = True
    if request.method == 'POST' and form.is_valid():
        try:
            for cot in ['ten', 'so_tien', 'ly_do']:
                setattr(de_xuat, cot, form.cleaned_data[cot])
            de_xuat.nguoi_de_xuat, de_xuat.thoi_gian_de_xuat = request.user, timezone.now()
            luu_de_xuat(de_xuat)
        except ValidationError as loi:
            form.add_error(None, loi)
        else:
            messages.success(request, 'Đã cập nhật khoản thưởng khác trong bản nháp.')
            return redirect('thuong:detail', bang.nguoi_dung.employee.pk, bang.nam, bang.thang)
    return render(request, 'thuong/propose.html', {'form': form, 'history': lich_su_de_xuat(request.user), 'editing_rejected': True})


def lich_su_de_xuat_trong_pham_vi(nguoi_dung):
    return DeXuatThuong.objects.select_related('bang_thuong').filter(
        bang_thuong__nguoi_dung__employee__in=nhan_vien_duoc_hien_thi(nguoi_dung),
        bang_thuong__trang_thai__in=['draft', 'rejected'])


@login_required
@require_POST
def xoa_de_xuat_thuong(request, bonus_id):
    if not co_vai_tro(request.user, NHAN_SU):
        return trang_tu_choi_truy_cap(request)
    de_xuat = get_object_or_404(lich_su_de_xuat_trong_pham_vi(request.user), pk=bonus_id)
    bang = de_xuat.bang_thuong
    try:
        xoa_de_xuat(de_xuat)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, 'Đã xóa khoản thưởng chưa được Giám đốc duyệt.')
    return redirect('thuong:detail', bang.nguoi_dung.employee.pk, bang.nam, bang.thang)


def ghi_lich_su(nguoi_dung, bang, noi_dung):
    LogEntry.objects.log_action(user_id=nguoi_dung.pk, content_type_id=ContentType.objects.get_for_model(Thuong).pk,
        object_id=str(bang.pk), object_repr=str(bang), action_flag=CHANGE, change_message=noi_dung)


@login_required
@require_POST
def gui_duyet_thuong(request, nam, thang):
    if not co_vai_tro(request.user, NHAN_SU):
        return trang_tu_choi_truy_cap(request)
    return xu_ly_bang_da_chon(request, nam, thang, gui_duyet=True)


@login_required
@require_POST
def xu_ly_duyet_thuong(request, nam, thang):
    if not co_vai_tro(request.user, GIAM_DOC):
        return trang_tu_choi_truy_cap(request)
    return xu_ly_bang_da_chon(request, nam, thang)


def xu_ly_bang_da_chon(request, nam, thang, gui_duyet=False):
    url = f"{reverse('thuong:list')}?thang={thang}&nam={nam}"
    thao_tac = 'submit' if gui_duyet else request.POST.get('action')
    if thao_tac not in ['submit', 'approve', 'reject']:
        messages.error(request, 'Lựa chọn duyệt không hợp lệ.')
        return redirect(url)
    ds = request.POST.getlist('nhan_vien_id') or request.POST.getlist('nhan_vien_ids')
    ds = list(dict.fromkeys(ds))
    ly_do = request.POST.get('ly_do', '').strip()
    if not ds:
        messages.error(request, 'Vui lòng chọn ít nhất một nhân viên.')
        return redirect(url)
    if thao_tac == 'reject' and len(ds) != 1:
        messages.error(request, 'Bạn chỉ có thể từ chối từng người. Vui lòng chọn một nhân viên và thực hiện từ chối riêng.')
        return redirect(url)
    try:
        ds = [int(ma) for ma in ds]
        with transaction.atomic():
            cac_bang = list(bang_thuong_trong_pham_vi(request.user).select_for_update().filter(
                nguoi_dung__employee__pk__in=ds, nam=nam, thang=thang,
                trang_thai__in=['draft', 'rejected'] if gui_duyet else ['pending']))
            if not cac_bang:
                raise ValidationError('Không có bảng thưởng hợp lệ trong số nhân viên đã chọn.')
            for bang in cac_bang:
                if gui_duyet:
                    gui_duyet_bang(bang)
                else:
                    duyet_bang(bang, request.user, tu_choi=thao_tac == 'reject', ly_do=ly_do)
                ghi_lich_su(request.user, bang, 'Gửi duyệt thưởng.' if gui_duyet else
                            (f'Từ chối thưởng. Lý do: {ly_do}' if thao_tac == 'reject' else 'Duyệt thưởng.'))
    except (ValueError, TypeError):
        messages.error(request, 'Danh sách nhân viên không hợp lệ.')
        return redirect(url)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
        return redirect(url)
    if thao_tac == 'approve':
        from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
        loi_luong = [cap_nhat_luong_nhan_vien(request.user, bang.nguoi_dung.employee.pk, nam, thang) for bang in cac_bang]
        loi_luong = [loi for loi in loi_luong if loi]
        if loi_luong:
            messages.warning(request, 'Chưa đủ điều kiện cập nhật lương: ' + ' | '.join(loi_luong[:5]))
    messages.success(request, {'submit': 'Gửi duyệt bảng thưởng thành công.',
        'approve': 'Duyệt bảng thưởng thành công.', 'reject': 'Đã từ chối khoản thưởng và lưu lý do.'}[thao_tac])
    return redirect(url)


@login_required
@require_POST
def xuat_bang_thuong(request):
    if not co_vai_tro(request.user, NHAN_SU, GIAM_DOC):
        return trang_tu_choi_truy_cap(request)
    form = BonusFilter(request.user, request.POST)
    if not form.is_valid() or not form.cleaned_data.get('thang') or not form.cleaned_data.get('nam'):
        messages.error(request, 'Vui lòng chọn tháng, năm và bộ lọc hợp lệ trước khi xuất bảng thưởng.')
        return redirect('thuong:list')
    du_lieu = {**form.cleaned_data, 'trang_thai': 'approved'}
    cac_bang = loc_bang_thuong(bang_thuong_trong_pham_vi(request.user), du_lieu)
    if not cac_bang.exists():
        messages.error(request, 'Chưa có dữ liệu thưởng đã duyệt để xuất.')
        return redirect('thuong:list')
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Mã nhân viên', 'Nhân viên', 'Phòng ban', 'Tháng', 'Năm', 'Loại thưởng', 'Khoản thưởng', 'Lý do', 'Số tiền', 'Trạng thái'])
    for bang in cac_bang:
        for khoan in cac_khoan_hien_thi(bang):
            writer.writerow([bang.nguoi_dung.employee.ma_ho_so, bang.nguoi_dung.employee.ho_va_ten, bang.nguoi_dung.employee.phong_ban.ten_phong_ban,
                bang.thang, bang.nam, khoan['ten'] if khoan['tu_dong'] else 'Thưởng khác',
                khoan['ten'], khoan['ly_do'], khoan['so_tien'], bang.get_trang_thai_display()])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="bonuses-{du_lieu["thang"]}-{du_lieu["nam"]}.csv"'
    return response
