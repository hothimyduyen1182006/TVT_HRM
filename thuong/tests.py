from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from bang_cong.models import ChotBangCong, TongHopCong
from bang_cong.services.chot_bang_cong_service import ChotBangCongService
from bang_luong.models import Luong
from bang_luong.services.tinh_luong_service import cap_nhat_luong_nhan_vien
from nhan_vien.access import NHAN_SU, GIAM_DOC, TRUONG_PHONG
from nhan_vien.models import PhongBan, NhanVien
from .models import DeXuatThuong, Thuong
from .services.quy_trinh import dong_bo_thuong_tu_dong, luu_de_xuat, xoa_de_xuat, gui_duyet_bang, duyet_bang


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
                thiet_lap_luong={'da_kiem_tra':True, 'luong_dong_bao_hiem':'0', 'ty_le_bao_hiem':{},
                    'can_cu_bao_hiem':'Căn cứ kiểm thử', 'doi_tuong_tinh_thue':'resident_2026', 'can_cu_thue':'Căn cứ kiểm thử'}))
        for employee in cls.people:
            TongHopCong.objects.create(nhan_vien=employee, thang=10, nam=2026,
                cong_chuan=22, cong_thuc_te=22, tong_cong=22)

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
        summary = TongHopCong.objects.get(nhan_vien=self.people[index], thang=10, nam=2026)
        ChotBangCong.objects.create(tong_hop=summary, nguoi_duyet=self.hr)
        summary.trang_thai = 'approved'
        summary.save()
        return dong_bo_thuong_tu_dong(self.people[index], 10, 2026)

    def proposal(self, bang, amount=750000):
        de_xuat = DeXuatThuong(bang_thuong=bang,ten='Thưởng dự án',so_tien=amount,
                                    ly_do='Hoàn thành dự án',nguoi_de_xuat=self.hr)
        luu_de_xuat(de_xuat)
        return de_xuat

    def test_attendance_approval_creates_summary_without_automatic_proposals(self):
        bang=self.approve_attendance()
        self.assertEqual(bang.thuong_chuyen_can,200000)
        self.assertEqual(bang.thuong_tham_nien,3000000)
        self.assertEqual(bang.tong_thuong,3200000)
        self.assertTrue(bang.ly_do_chuyen_can)
        self.assertTrue(bang.ly_do_tham_nien)
        self.assertEqual(bang.trang_thai,'draft')
        self.assertFalse(DeXuatThuong.objects.exists())
        self.assertFalse(Luong.objects.exists())

    def test_whole_period_approval_updates_all_employees(self):
        ChotBangCongService.chot_bang_cong(10, 2026, self.hr)
        for employee in self.people:
            dong_bo_thuong_tu_dong(employee, 10, 2026)
        self.assertEqual(Thuong.objects.filter(thuong_chuyen_can=200000).count(),2)
        self.assertFalse(DeXuatThuong.objects.exists())

    def test_unapproved_or_incomplete_attendance_cannot_be_submitted(self):
        bang=dong_bo_thuong_tu_dong(self.people[0],10,2026)
        self.assertIsNone(bang.ly_do_chuyen_can)
        with self.assertRaises(ValidationError):
            gui_duyet_bang(bang)
        self.assertEqual(Thuong.objects.get(pk=bang.pk).trang_thai,'draft')

    def test_absence_or_leave_removes_attendance_bonus(self):
        for index,state in enumerate(['absent','leave']):
            changes = {'cong_nghi_co_luong': 1} if state == 'leave' else {'so_ngay_khong_phep': 1}
            TongHopCong.objects.filter(nhan_vien=self.people[index]).update(**changes)
            bang=self.approve_attendance(index)
            self.assertEqual(bang.thuong_chuyen_can,0)
            self.assertTrue(bang.ly_do_chuyen_can)

    def test_proposal_create_edit_delete_recomputes_total(self):
        bang=self.approve_attendance()
        proposal=self.proposal(bang)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,750000)
        self.assertEqual(bang.tong_thuong,3950000)
        proposal.so_tien=500000
        luu_de_xuat(proposal)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,500000)
        xoa_de_xuat(proposal)
        bang.refresh_from_db()
        self.assertEqual(bang.thuong_khac,0)
        self.assertEqual(bang.tong_thuong,3200000)

    def test_partial_workday_does_not_receive_attendance_bonus(self):
        TongHopCong.objects.filter(nhan_vien=self.people[0]).update(cong_thuc_te=Decimal('21.5'))
        bang=self.approve_attendance()
        self.assertEqual(bang.thuong_chuyen_can,0)
        self.assertIn('chưa đủ ngày công',bang.ly_do_chuyen_can)

    def test_rejected_automatic_only_board_can_be_resubmitted(self):
        bang=self.approve_attendance()
        self.post(self.hr,self.submit_url,{'nhan_vien_ids':[self.people[0].pk]})
        self.post(self.director,self.decision_url,{'action':'reject',
            'nhan_vien_ids':[self.people[0].pk],'ly_do':'Kiểm tra lại công'})
        self.client.force_login(self.hr)
        response=self.client.get(self.list_url,{'thang':10,'nam':2026})
        self.assertContains(response,'id="bm-submit-form"')
        self.assertEqual(self.post(self.hr,self.submit_url,{'nhan_vien_ids':[self.people[0].pk]}).status_code,302)
        bang.refresh_from_db()
        self.assertEqual(bang.trang_thai,'pending')
        self.assertIsNone(bang.nguoi_duyet)
        self.assertIsNone(bang.ngay_duyet)
        self.assertFalse(bang.ly_do_tu_choi)
        self.assertEqual(LogEntry.objects.filter(object_id=bang.pk).count(),3)
        self.assertFalse(Luong.objects.exists())

    def test_approval_ignores_drafts_and_does_not_approve_twice(self):
        bang=self.approve_attendance()
        self.approve_attendance(1)
        gui_duyet_bang(bang)
        data={'action':'approve','nhan_vien_ids':[p.pk for p in self.people]}
        self.post(self.director,self.decision_url,data)
        self.post(self.director,self.decision_url,data)
        bang.refresh_from_db()
        self.assertEqual(bang.trang_thai,'approved')
        self.assertEqual(Thuong.objects.get(nguoi_dung=self.people[1].nguoi_dung).trang_thai,'draft')
        self.assertEqual(LogEntry.objects.filter(object_id=bang.pk).count(),1)
        from .services.tinh_toan import cac_khoan_thuong_tinh_luong
        amounts = cac_khoan_thuong_tinh_luong(self.people[0].pk, 2026, 10)
        self.assertEqual(sum(Decimal(item['amount']) for item in amounts), 3200000)

    def test_submission_and_selected_approval_flow_updates_payroll_once(self):
        bang=self.approve_attendance()
        other=self.approve_attendance(1)
        self.proposal(bang)
        self.assertEqual(self.post(self.hr,self.submit_url,{'nhan_vien_ids':[p.pk for p in self.people]}).status_code,302)
        self.assertFalse(Luong.objects.exclude(tong_tien_thuong=0).exists())
        response=self.post(self.director,self.decision_url,{'action':'approve','nhan_vien_ids':[self.people[0].pk]})
        self.assertEqual(response.status_code,302)
        bang.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(bang.trang_thai,'approved')
        self.assertEqual(other.trang_thai,'pending')
        self.assertFalse(Luong.objects.exists())
        self.assertEqual(bang.nguoi_duyet,self.director)
        from .services.tinh_toan import cac_khoan_thuong_tinh_luong
        amounts = cac_khoan_thuong_tinh_luong(self.people[0].pk, 2026, 10)
        self.assertEqual(sum(Decimal(item['amount']) for item in amounts), 3950000)
        cap_nhat_luong_nhan_vien(self.hr,self.people[0].pk,2026,10)
        self.assertFalse(Luong.objects.exists())
        self.assertTrue(LogEntry.objects.filter(user=self.director,object_id=bang.pk).exists())

    def test_rejection_requires_reason_and_rejects_only_one_employee(self):
        for i in range(2):
            bang=self.approve_attendance(i); gui_duyet_bang(bang)
        self.post(self.director,self.decision_url,{'action':'reject','nhan_vien_ids':[p.pk for p in self.people],'ly_do':'Kiểm tra lại'})
        self.assertEqual(Thuong.objects.filter(trang_thai='pending').count(),2)
        self.post(self.director,self.decision_url,{'action':'reject','nhan_vien_ids':[self.people[0].pk]})
        self.assertEqual(Thuong.objects.filter(trang_thai='pending').count(),2)
        self.post(self.director,self.decision_url,{'action':'reject','nhan_vien_ids':[self.people[0].pk],'ly_do':'Đối chiếu dự án'})
        bang=Thuong.objects.get(nguoi_dung=self.people[0].nguoi_dung)
        self.assertEqual(bang.trang_thai,'rejected')
        self.assertEqual(bang.ly_do_tu_choi,'Đối chiếu dự án')
        self.assertFalse(Luong.objects.exists())
        response=self.client.get(reverse('thuong:detail',args=[self.people[0].pk,2026,10]))
        self.assertContains(response,'Đối chiếu dự án')

    def test_pending_and_approved_proposals_cannot_be_changed(self):
        bang=self.approve_attendance()
        proposal=self.proposal(bang)
        bang.refresh_from_db(); gui_duyet_bang(bang)
        for state in ['pending','approved']:
            if state=='approved':
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
        ma_hien_thi = f'MT_202610_{bang.nguoi_dung_id}'
        self.assertContains(response,ma_hien_thi)
        self.assertNotContains(response,bang.ma_thuong)
        self.assertTrue(Thuong.objects.filter(pk=bang.pk).exists())
        for url in [reverse('thuong:propose'),reverse('thuong:proposal-edit',args=[proposal.pk]),
                    reverse('thuong:detail',args=[self.people[0].pk,2026,10]), reverse('home')]:
            self.assertEqual(self.client.get(url).status_code,200,url)
        self.client.force_login(self.people[0].nguoi_dung)
        response=self.client.get(reverse('thuong:personal'),{'thang':10,'nam':2026})
        self.assertContains(response,ma_hien_thi)
        bang.refresh_from_db(); gui_duyet_bang(bang); duyet_bang(bang,self.director)
        response=self.post(self.hr,reverse('thuong:export'),{'thang':10,'nam':2026,'trang_thai':'approved'})
        self.assertEqual(response.status_code,200)
        self.assertIn('Thưởng dự án',response.content.decode('utf-8-sig'))

    def test_roles_scope_and_csrf_are_enforced(self):
        bang=self.approve_attendance(); gui_duyet_bang(bang)
        self.assertEqual(self.post(self.people[0].nguoi_dung,self.decision_url,
            {'action':'approve','nhan_vien_ids':[self.people[0].pk]}).status_code,403)
        self.client.force_login(self.director)
        self.assertEqual(self.client.post(self.decision_url,{'action':'approve','nhan_vien_ids':[self.people[0].pk]}).status_code,403)
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

    def test_approval_keeps_payroll_and_reports_recalculation_warning(self):
        bang = self.approve_attendance()
        summary = TongHopCong.objects.get(nhan_vien=self.people[0])
        phieu = Luong.objects.create(tong_hop=summary, tong_thuong=bang,
            luong_co_ban=10000000, luong_theo_cong=10000000,
            luong_thuc_linh=10000000)
        selected = {'nhan_vien_ids': [self.people[0].pk]}
        self.post(self.hr, self.submit_url, selected)
        response = self.post(self.director, self.decision_url, {**selected, 'action': 'approve'})
        bang.refresh_from_db()
        phieu.refresh_from_db()
        self.assertEqual(bang.trang_thai, 'approved')
        self.assertEqual(phieu.tong_tien_thuong, 0)
        self.assertEqual(phieu.luong_thuc_linh, 10000000)
        self.assertTrue(cap_nhat_luong_nhan_vien(self.hr, self.people[0].pk, 2026, 10))
        self.assertTrue(any('tính lại' in str(message) for message in response.wsgi_request._messages))

    def test_submission_rolls_back_when_one_board_lacks_basis(self):
        first = self.approve_attendance()
        second = dong_bo_thuong_tu_dong(self.people[1], 10, 2026)
        self.post(self.hr, self.submit_url, {'nhan_vien_ids': [p.pk for p in self.people]})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.trang_thai, 'draft')
        self.assertEqual(second.trang_thai, 'draft')
        self.assertFalse(LogEntry.objects.exists())

    def test_duplicate_proposal_does_not_overwrite_existing_amount(self):
        bang = self.approve_attendance()
        item = self.proposal(bang)
        self.post(self.hr, reverse('thuong:propose'), {
            'nhan_vien': self.people[0].pk, 'thang': 10, 'nam': 2026,
            'ten': item.ten, 'ly_do': 'Thay đổi', 'so_tien': '100000',
        })
        item.refresh_from_db()
        self.assertEqual(item.so_tien, 750000)
        self.assertEqual(bang.de_xuat.count(), 1)
        item.ten = 'Project'
        luu_de_xuat(item)
        duplicate = DeXuatThuong(bang_thuong=bang, ten='PROJECT', so_tien=100000,
            ly_do='Thay đổi', nguoi_de_xuat=self.hr)
        with self.assertRaises(ValidationError):
            luu_de_xuat(duplicate)

    def test_export_requires_approved_filter_and_escapes_formula(self):
        bang = self.approve_attendance()
        item = self.proposal(bang)
        item.ly_do = '=SUM(1,2)'
        luu_de_xuat(item)
        bang.refresh_from_db()
        gui_duyet_bang(bang)
        duyet_bang(bang, self.director)
        url = reverse('thuong:export')
        for status in ['', 'pending', 'draft', 'rejected']:
            response = self.post(self.hr, url, {'thang': 10, 'nam': 2026, 'trang_thai': status})
            self.assertEqual(response.status_code, 302)
        response = self.post(self.hr, url, {'thang': 10, 'nam': 2026, 'trang_thai': 'approved'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('bonuses-2026-10.csv', response['Content-Disposition'])
        self.assertIn("'=SUM(1,2)", response.content.decode('utf-8-sig'))

    def test_database_rejects_inconsistent_total(self):
        bang=self.approve_attendance()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Thuong.objects.filter(pk=bang.pk).update(tong_thuong=1)
