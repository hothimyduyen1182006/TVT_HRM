from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nhan_vien.access import GIAM_DOC, NHAN_SU, TRUONG_PHONG, co_vai_tro, nhan_vien_duoc_hien_thi
from nhan_vien.models import NhanVien
from .forms import BonusFilter, BonusProposalForm, PersonalBonusFilter
from .models import Thuong
from .services.hien_thi import (
    bang_thuong_trong_pham_vi, cac_khoan_hien_thi, gan_ma_hien_thi,
    lich_su_de_xuat, lich_su_de_xuat_trong_pham_vi, loc_bang_thuong,
)
from .services import quy_trinh
from .services.xuat_tep import tao_tep_thuong


def trang_tu_choi_truy_cap(request):
    return render(request, 'thuong/access_denied.html', status=403)


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
            quy_trinh.dong_bo_thuong_tu_dong(nhan_vien, ky['thang'], ky['nam'])
    bang_trong_ky = bang_thuong_trong_pham_vi(request.user)
    if co_vai_tro(request.user, GIAM_DOC):
        bang_trong_ky = bang_trong_ky.exclude(trang_thai='draft')
    bang_trong_ky = loc_bang_thuong(bang_trong_ky, {cot: ky.get(cot) for cot in ('thang', 'nam')})
    cac_bang = loc_bang_thuong(bang_trong_ky, ky) if form.is_valid() else Thuong.objects.none()
    tong = cac_bang.aggregate(tong=Sum('tong_thuong'))['tong'] or Decimal(0)
    trang = Paginator(cac_bang, 5).get_page(request.GET.get('page'))
    tham_so = request.GET.copy()
    tham_so.pop('page', None)
    co_ky = bool(ky.get('thang') and ky.get('nam'))
    return render(request, 'thuong/list_redesign.html', {
        'form': form, 'rows': gan_ma_hien_thi(trang.object_list), 'page_obj': trang, 'page_query': tham_so.urlencode(),
        'khong_co_du_lieu_ky': (
            form.is_valid()
            and not any(ky.get(cot) for cot in ('tu_khoa', 'nhan_vien', 'phong_ban'))
            and not trang.paginator.count
            and not bang_trong_ky.exists()
        ),
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


@login_required
def de_xuat_thuong_khac(request):
    if not co_vai_tro(request.user, NHAN_SU, TRUONG_PHONG):
        return trang_tu_choi_truy_cap(request)
    form = BonusProposalForm(request.user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        du_lieu = form.cleaned_data
        try:
            bang = quy_trinh.tao_de_xuat_thuong(request.user, du_lieu)
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
            quy_trinh.cap_nhat_de_xuat_tu_form(de_xuat, form.cleaned_data, request.user)
        except ValidationError as loi:
            form.add_error(None, loi)
        else:
            messages.success(request, 'Đã cập nhật khoản thưởng khác trong bản nháp.')
            return redirect('thuong:detail', bang.nguoi_dung.employee.pk, bang.nam, bang.thang)
    return render(request, 'thuong/propose.html', {'form': form, 'history': lich_su_de_xuat(request.user), 'editing_rejected': True})


@login_required
@require_POST
def xoa_de_xuat_thuong(request, bonus_id):
    if not co_vai_tro(request.user, NHAN_SU):
        return trang_tu_choi_truy_cap(request)
    de_xuat = get_object_or_404(lich_su_de_xuat_trong_pham_vi(request.user), pk=bonus_id)
    bang = de_xuat.bang_thuong
    try:
        quy_trinh.xoa_de_xuat(de_xuat)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
    else:
        messages.success(request, 'Đã xóa khoản thưởng chưa được Giám đốc duyệt.')
    return redirect('thuong:detail', bang.nguoi_dung.employee.pk, bang.nam, bang.thang)


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
        cac_bang = quy_trinh.duyet_cac_bang(
            request.user, ds, nam, thang, thao_tac, ly_do, gui_duyet=gui_duyet,
        )
    except (ValueError, TypeError):
        messages.error(request, 'Danh sách nhân viên không hợp lệ.')
        return redirect(url)
    except ValidationError as loi:
        messages.error(request, '; '.join(loi.messages))
        return redirect(url)
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
    du_lieu = form.cleaned_data
    if du_lieu.get('trang_thai') != 'approved':
        messages.error(request, 'Vui lòng lọc trạng thái Đã duyệt trước khi xuất CSV.')
        return redirect('thuong:list')
    cac_bang = loc_bang_thuong(bang_thuong_trong_pham_vi(request.user), du_lieu)
    if not cac_bang.exists():
        messages.error(request, 'Chưa có dữ liệu thưởng đã duyệt để xuất.')
        return redirect('thuong:list')
    return tao_tep_thuong(cac_bang, du_lieu['nam'], du_lieu['thang'])
