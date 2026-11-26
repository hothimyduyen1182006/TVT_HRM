import csv
import io
from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from bang_cong.models import ChamCong, ChotBangCong, TongHopCong
from bang_cong.services.chot_bang_cong_service import duyet_cong_nhan_vien, ky_cong_da_khoa
from bang_luong.models import Luong
from nhan_vien.access import NHAN_SU, GIAM_DOC, TRUONG_PHONG
from nhan_vien.models import PhongBan, NhanVien
from nghi_phep.models import DonNghiPhep, NgayNghi
from .models import DeXuatThuong, Thuong
from .services.quy_trinh import dong_bo_thuong_tu_dong, luu_de_xuat, xoa_de_xuat, gui_duyet_bang, duyet_bang
from .services.tinh_toan import tinh_thuong_tham_nien


class SeniorityBonusTests(SimpleTestCase):
    def test_uses_flat_rate_at_completed_year_thresholds(self):
        cases = [
            (date(2025, 11, 1), 0),
            (date(2025, 10, 31), 150000),
            (date(2023, 11, 1), 150000),
            (date(2023, 10, 31), 200000),
            (date(2021, 11, 1), 200000),
            (date(2021, 10, 31), 500000),
            (date(2020, 1, 1), 500000),
        ]
        for start_date, expected in cases:
            with self.subTest(start_date=start_date):
                employee = NhanVien(ngay_vao_lam=start_date)
                self.assertEqual(tinh_thuong_tham_nien(employee, 10, 2026)[2], expected)


class BonusWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.hr = get_user_model().objects.create_user('hr')
        cls.director = get_user_model().objects.create_user('director')
        for user, role in [(cls.hr, NHAN_SU), (cls.director, GIAM_DOC)]:
            user.groups.add(Group.objects.get_or_create(name=role)[0])
        phong = PhongBan.objects.create(ma_phong_ban='A', ten_phong_ban='Phòng A')
        cls.people = []
        for i in range(2):
            user = get_user_model().objects.create_user(f'employee{i}')
            cls.people.append(NhanVien.objects.create(nguoi_dung=user, ma_ho_so=f'NV{i}', ho_va_ten=f'Nhân viên {i}',
                phong_ban=phong, ngay_vao_lam=date(2020,1,1), luong_co_ban=10000000,
                thiet_lap_luong={'da_kiem_tra':True, 'luong_dong_bao_hiem':'8000000',
                    'can_cu_bao_hiem':'Căn cứ kiểm thử', 'doi_tuong_tinh_thue':'resident_2026', 'can_cu_thue':'Căn cứ kiểm thử'}))
        cls.ma_ky_cong = 202610
        for so_ngay in range(1, 25):
            for employee in cls.people:
                ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 10, so_ngay), trang_thai='present',
                    gio_vao=time(8), gio_ra=time(17), so_gio_lam=8)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.list_url = reverse('thuong:list')
        self.decision_url = reverse('thuong:decision', args=[2026,10])
        self.submit_url = reverse('thuong:submit', args=[2026,10])

    def post(self, user, url, data):
        self.client.force_login(user)
        self.client.get(reverse('login'))
        return self.client.post(url,data,HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def approve_attendance(self, index=0):
        duyet_cong_nhan_vien(self.hr,self.people[index],self.ma_ky_cong)
        return Thuong.objects.get(nguoi_dung=self.people[index].nguoi_dung,thang=10,nam=2026)

    def proposal(self, bang, amount=750000):
        de_xuat = DeXuatThuong(bang_thuong=bang,ten='Thưởng dự án',so_tien=amount,
                                    ly_do='Hoàn thành dự án',nguoi_de_xuat=self.hr)
        luu_de_xuat(de_xuat)
        return de_xuat

    def test_attendance_approval_creates_summary_without_automatic_proposals(self):
        bang=self.approve_attendance()
        self.assertEqual(bang.thuong_chuyen_can,200000)
        self.assertEqual(bang.thuong_tham_nien,500000)
        self.assertEqual(bang.tong_thuong,700000)
        self.assertTrue(bang.ly_do_chuyen_can)
        self.assertTrue(bang.ly_do_tham_nien)
        self.assertEqual(bang.trang_thai,'ban_nhap')
        self.assertFalse(DeXuatThuong.objects.exists())
        self.assertFalse(Luong.objects.exists())

    def test_attendance_closing_only_updates_selected_employee(self):
        url = reverse('bang_cong:chot-nhan-vien-da-chon', args=[self.ma_ky_cong])
        response = self.post(self.hr, url, {'nhan_vien': [self.people[0].pk]})

        self.assertEqual(response.status_code, 302)
        self.assertQuerySetEqual(
            ChotBangCong.objects.values_list('tong_hop__nhan_vien_id', flat=True),
            [self.people[0].pk],
        )
        self.assertTrue(Thuong.objects.filter(
            nguoi_dung=self.people[0].nguoi_dung, thuong_chuyen_can=200000,
        ).exists())
        self.assertFalse(Thuong.objects.filter(nguoi_dung=self.people[1].nguoi_dung).exists())
        self.assertFalse(DeXuatThuong.objects.exists())

    def test_attendance_closing_requires_a_selection(self):
        url = reverse('bang_cong:chot-nhan-vien-da-chon', args=[self.ma_ky_cong])
        response = self.post(self.hr, url, {})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChotBangCong.objects.exists())

    def test_attendance_lock_requires_the_employees_own_closing_record(self):
        NhanVien.objects.filter(pk=self.people[1].pk).update(dang_hoat_dong=False)
        self.approve_attendance()

        self.assertTrue(ky_cong_da_khoa(2026, 10, self.people[0].pk))
        self.assertFalse(ky_cong_da_khoa(2026, 10, self.people[1].pk))

    def test_incomplete_attendance_blocks_closing_and_rolls_back_summary(self):
        nhan_vien = self.people[0]
        ChamCong.objects.filter(nhan_vien=nhan_vien, ngay=date(2026, 10, 1)).update(
            trang_thai='incomplete', gio_ra=None,
        )

        with self.assertRaises(ValidationError):
            duyet_cong_nhan_vien(self.hr, nhan_vien, self.ma_ky_cong)

        self.assertFalse(TongHopCong.objects.filter(nhan_vien=nhan_vien).exists())
        self.assertFalse(ChotBangCong.objects.exists())

    def test_attendance_closing_rolls_back_if_a_selected_employee_has_no_records(self):
        ChamCong.objects.filter(nhan_vien=self.people[1]).delete()
        url = reverse('bang_cong:chot-nhan-vien-da-chon', args=[self.ma_ky_cong])
        response = self.post(self.hr, url, {'nhan_vien': [person.pk for person in self.people]})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChotBangCong.objects.exists())
        self.assertFalse(Thuong.objects.exists())

    def test_unapproved_or_incomplete_attendance_cannot_be_submitted(self):
        bang=dong_bo_thuong_tu_dong(self.people[0],10,2026)
        self.assertIsNone(bang.ly_do_chuyen_can)
        with self.assertRaises(ValidationError):
            gui_duyet_bang(bang)
        self.assertEqual(Thuong.objects.get(pk=bang.pk).trang_thai,'ban_nhap')

    def test_absence_or_leave_removes_attendance_bonus(self):
        for index,state in enumerate(['absent','leave']):
            if state == 'leave':
                don = DonNghiPhep.objects.create(nhan_vien=self.people[index], ngay_bat_dau=date(2026,10,5), ngay_ket_thuc=date(2026,10,5), ly_do='Nghỉ phép đã duyệt', trang_thai='da_duyet')
                NgayNghi.objects.create(don_nghi_phep=don, ngay=date(2026,10,5))
            ChamCong.objects.filter(nhan_vien=self.people[index],ngay=date(2026,10,5)).update(
                trang_thai=state,gio_vao=None,gio_ra=None)
            bang=self.approve_attendance(index)
            self.assertEqual(bang.thuong_chuyen_can,0)
            self.assertTrue(bang.ly_do_chuyen_can)

    def test_proposal_create_edit_delete_recomputes_total(self):
        bang=self.approve_attendance()
        proposal=self.proposal(bang)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,750000)
        self.assertEqual(bang.tong_thuong,1450000)
        proposal.so_tien=500000
        luu_de_xuat(proposal)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,500000)
        xoa_de_xuat(proposal)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,0)
        self.assertEqual(bang.tong_thuong,700000)

    def test_partial_workday_does_not_receive_attendance_bonus(self):
        ChamCong.objects.filter(nhan_vien=self.people[0],ngay=date(2026,10,5)).update(gio_ra=time(12))
        bang=self.approve_attendance()
        self.assertEqual(bang.thuong_chuyen_can,0)
        self.assertIn('chưa đủ ngày công',bang.ly_do_chuyen_can)

    def test_rejected_automatic_only_board_can_be_resubmitted(self):
        bang=self.approve_attendance()
        self.post(self.hr,self.submit_url,{'nhan_vien_ids':[self.people[0].pk]})
        self.post(self.director,self.decision_url,{'thao_tac':'tu_choi',
            'nhan_vien_ids':[self.people[0].pk],'ly_do':'Kiểm tra lại công'})
        self.client.force_login(self.hr)
        response=self.client.get(self.list_url,{'thang':10,'nam':2026})
        self.assertContains(response,'id="bm-submit-form"')
        self.assertEqual(self.post(self.hr,self.submit_url,{'nhan_vien_ids':[self.people[0].pk]}).status_code,302)
        bang.refresh_from_db()
        self.assertEqual(bang.trang_thai,'cho_duyet')
        self.assertIsNone(bang.nguoi_duyet)
        self.assertIsNone(bang.ngay_duyet)
        self.assertFalse(bang.ly_do_tu_choi)
        self.assertEqual(LogEntry.objects.filter(object_id=bang.pk).count(),3)
        self.assertFalse(Luong.objects.exists())

    def test_approval_ignores_drafts_and_does_not_approve_twice(self):
        bang=self.approve_attendance()
        self.approve_attendance(1)
        gui_duyet_bang(bang)
        data={'thao_tac':'duyet','nhan_vien_ids':[p.pk for p in self.people]}
        self.post(self.director,self.decision_url,data)
        self.post(self.director,self.decision_url,data)
        bang.refresh_from_db()
        self.assertEqual(bang.trang_thai,'da_duyet')
        self.assertEqual(Thuong.objects.get(nguoi_dung=self.people[1].nguoi_dung).trang_thai,'ban_nhap')
        self.assertEqual(LogEntry.objects.filter(object_id=bang.pk).count(),1)
        self.assertEqual(bang.tong_thuong,700000)
        self.assertFalse(Luong.objects.exists())

    def test_submission_and_selected_approval_does_not_create_payroll(self):
        bang=self.approve_attendance()
        other=self.approve_attendance(1)
        self.proposal(bang)
        self.assertEqual(self.post(self.hr,self.submit_url,{'nhan_vien_ids':[p.pk for p in self.people]}).status_code,302)
        self.assertFalse(Luong.objects.exclude(tong_tien_thuong=0).exists())
        response=self.post(self.director,self.decision_url,{'thao_tac':'duyet','nhan_vien_ids':[self.people[0].pk]})
        self.assertEqual(response.status_code,302)
        bang.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(bang.trang_thai,'da_duyet')
        self.assertEqual(other.trang_thai,'cho_duyet')
        self.assertFalse(Luong.objects.filter(tong_hop__nhan_vien=self.people[1]).exists())
        self.assertEqual(bang.nguoi_duyet,self.director)
        self.assertEqual(bang.tong_thuong,1450000)
        self.assertFalse(Luong.objects.exists())
        self.assertTrue(LogEntry.objects.filter(user=self.director,object_id=bang.pk).exists())

    def test_rejection_requires_reason_and_rejects_only_one_employee(self):
        for i in range(2):
            bang=self.approve_attendance(i); gui_duyet_bang(bang)
        self.post(self.director,self.decision_url,{'thao_tac':'tu_choi','nhan_vien_ids':[p.pk for p in self.people],'ly_do':'Kiểm tra lại'})
        self.assertEqual(Thuong.objects.filter(trang_thai='cho_duyet').count(),2)
        self.post(self.director,self.decision_url,{'thao_tac':'tu_choi','nhan_vien_ids':[self.people[0].pk]})
        self.assertEqual(Thuong.objects.filter(trang_thai='cho_duyet').count(),2)
        self.post(self.director,self.decision_url,{'thao_tac':'tu_choi','nhan_vien_ids':[self.people[0].pk],'ly_do':'Đối chiếu dự án'})
        bang=Thuong.objects.get(nguoi_dung=self.people[0].nguoi_dung)
        self.assertEqual(bang.trang_thai,'tu_choi')
        self.assertEqual(bang.ly_do_tu_choi,'Đối chiếu dự án')
        self.assertFalse(Luong.objects.exists())
        response=self.client.get(reverse('thuong:detail',args=[self.people[0].pk,2026,10]))
        self.assertContains(response,'Đối chiếu dự án')

    def test_pending_and_approved_proposals_cannot_be_changed(self):
        bang=self.approve_attendance()
        proposal=self.proposal(bang)
        bang.refresh_from_db(); gui_duyet_bang(bang)
        for state in ['cho_duyet','da_duyet']:
            if state=='da_duyet':
                duyet_bang(bang,self.director)
            proposal.so_tien=900000
            with self.assertRaises(ValidationError): luu_de_xuat(proposal)
            with self.assertRaises(ValidationError): xoa_de_xuat(proposal)
        proposal.refresh_from_db()
        self.assertEqual(proposal.so_tien,750000)

    def test_list_personal_detail_proposal_and_export_render(self):
        bang=self.approve_attendance(); proposal=self.proposal(bang)
        self.client.force_login(self.hr)
        response=self.client.get(self.list_url,{'thang':10,'nam':2026})
        ma_hien_thi = f'MT2610-{bang.nguoi_dung_id:03d}'
        self.assertContains(response,ma_hien_thi)
        self.assertEqual(bang.pk, ma_hien_thi)
        self.assertIsInstance(proposal.pk, int)
        self.assertTrue(Thuong.objects.filter(pk=bang.pk).exists())
        for url in [reverse('thuong:propose'),reverse('thuong:proposal-edit',args=[proposal.pk]),
                    reverse('thuong:detail',args=[self.people[0].pk,2026,10]), reverse('home')]:
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.client.force_login(self.people[0].nguoi_dung)
        response=self.client.get(reverse('thuong:personal'),{'thang':10,'nam':2026})
        self.assertContains(response,ma_hien_thi)
        bang.refresh_from_db(); gui_duyet_bang(bang); duyet_bang(bang,self.director)
        response=self.post(self.hr,reverse('thuong:export'),{'thang':10,'nam':2026,'trang_thai':'da_duyet'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        tieu_de, dong = csv.reader(io.StringIO(response.content.decode('utf-8-sig')))
        self.assertEqual(tieu_de, [
            'Mã thưởng', 'Họ và tên', 'Phòng ban', 'Thưởng chuyên cần',
            'Thưởng thâm niên', 'Thưởng khác', 'Tổng thưởng', 'Trạng thái', 'Ngày duyệt',
        ])
        self.assertEqual(dong[0], ma_hien_thi)
        self.assertEqual(Decimal(dong[5]), proposal.so_tien)
        self.assertEqual(Decimal(dong[6]), bang.tong_thuong)
        self.assertEqual(dong[7], 'Đã duyệt')
        self.assertRegex(dong[8], r'^\d{2}/\d{2}/\d{4}$')

    def test_roles_scope_and_csrf_are_enforced(self):
        bang=self.approve_attendance(); gui_duyet_bang(bang)
        self.assertEqual(self.post(self.people[0].nguoi_dung,self.decision_url,
            {'thao_tac':'duyet','nhan_vien_ids':[self.people[0].pk]}).status_code,403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(self.decision_url,{'thao_tac':'duyet','nhan_vien_ids':[self.people[0].pk]}).status_code,403)
        self.client.force_login(self.people[1].nguoi_dung)
        self.assertEqual(self.client.get(reverse('thuong:detail',args=[self.people[0].pk,2026,10])).status_code,403)

    def test_home_bonus_shortcut_follows_role_and_keeps_position(self):
        for user, target in [(self.hr,'thuong:list'), (self.director,'thuong:list'),
                             (self.people[0].nguoi_dung,'thuong:personal')]:
            self.client.force_login(user)
            response=self.client.get(reverse('home'))
            self.assertEqual(response.context['bonus_url'],reverse(target))
            html=response.content.decode()
            self.assertLess(html.index('Xem bảng công'),html.index('Xem bảng thưởng'))
            self.assertLess(html.index('Xem bảng thưởng'),html.index('Xem bảng lương'))

    def test_bonus_to_payroll_submission_approval_and_payment(self):
        from bang_luong.services.tinh_luong_service import (
            duyet_toan_bo_bang_luong, gui_bang_luong_cho_giam_doc, tinh_bang_luong,
        )
        for i in range(2):
            self.approve_attendance(i)
        selected={'nhan_vien_ids':[p.pk for p in self.people]}
        self.post(self.hr,self.submit_url,selected)
        self.post(self.director,self.decision_url,{**selected,'thao_tac':'duyet'})
        self.assertFalse(Luong.objects.exists())
        self.assertEqual(tinh_bang_luong(self.hr, 2026, 10), 2)
        self.assertEqual(Luong.objects.filter(tong_tien_thuong=700000).count(),2)
        gui_bang_luong_cho_giam_doc(self.hr, 2026, 10)
        duyet_toan_bo_bang_luong(self.director, 2026, 10)

        self.assertEqual(Luong.objects.filter(trang_thai='Da_duyet').count(),2)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse('bang_luong:danh_sach'),{'month':10,'year':2026}).status_code,200)
        self.client.force_login(self.people[0].nguoi_dung)
        phieu=Luong.objects.get(tong_hop__nhan_vien=self.people[0])
        self.assertEqual(self.client.get(reverse('bang_luong:chi_tiet',args=[phieu.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('home')).status_code,200)

    def test_database_rejects_inconsistent_total(self):
        bang=self.approve_attendance()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Thuong.objects.filter(pk=bang.pk).update(tong_thuong=1)
