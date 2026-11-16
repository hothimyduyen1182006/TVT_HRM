from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from bang_cong.models import ChamCong
from bang_cong.services.quy_trinh import duyet_cong_nhan_vien, xu_ly_trang_thai_ky_cong
from bang_cong.services.tinh_toan import lich_thang
from bang_luong.models import Luong
from bang_cong.thang_lich import thang_lich
from bang_luong.services.tinh_toan import cap_nhat_luong_nhan_vien
from nhan_vien.access import NHAN_SU, GIAM_DOC, TRUONG_PHONG
from nhan_vien.models import PhongBan, NhanVien
from nghi_phep.models import LeaveDay
from .models import DeXuatThuong, Thuong
from .views import dong_bo_thuong_tu_dong, luu_de_xuat, xoa_de_xuat, gui_duyet_bang, duyet_bang


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
        cls.period = thang_lich(2026,10)
        for lich in lich_thang(2026,10,cls.period).values():
            if lich.loai_ngay == 'work':
                for employee in cls.people:
                    ChamCong.objects.create(nhan_vien=employee, ngay=lich.ngay, trang_thai='present',
                        gio_vao=time(8),gio_ra=time(17),so_gio_lam=8)

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
        duyet_cong_nhan_vien(self.hr,self.people[index],self.period.pk)
        return Thuong.objects.get(nguoi_dung=self.people[index].nguoi_dung,thang=10,nam=2026)

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
        phieu=Luong.objects.get(tong_hop__nhan_vien=self.people[0])
        self.assertEqual(phieu.tong_tien_thuong,0)

    def test_whole_period_approval_updates_all_employees(self):
        xu_ly_trang_thai_ky_cong(self.director,self.period.pk,'approve','Đã đối chiếu công')
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
            if state == 'leave':
                LeaveDay.objects.create(employee=self.people[index], date=date(2026,10,5),
                    units=1, paid=True, reason='Nghỉ phép đã duyệt', approved=True)
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
        ChamCong.objects.filter(nhan_vien=self.people[0],ngay=date(2026,10,5)).update(gio_ra=time(12))
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
        self.assertEqual(Luong.objects.get(tong_hop__nhan_vien=self.people[0]).tong_tien_thuong,0)

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
        self.assertEqual(Luong.objects.get(tong_hop__nhan_vien=self.people[0]).tong_tien_thuong,3200000)

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
        self.assertEqual(Luong.objects.get(tong_hop__nhan_vien=self.people[1]).tong_tien_thuong,0)
        self.assertEqual(bang.nguoi_duyet,self.director)
        phieu=Luong.objects.get(tong_hop__nhan_vien=self.people[0])
        self.assertEqual(phieu.tong_tien_thuong,3950000)
        self.assertEqual(phieu.tong_thuong_id,bang.pk)
        cap_nhat_luong_nhan_vien(self.hr,self.people[0].pk,2026,10)
        phieu.refresh_from_db()
        self.assertEqual(phieu.tong_tien_thuong,3950000)
        self.assertEqual(Luong.objects.filter(tong_hop__nhan_vien=self.people[0]).count(),1)
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
        self.assertEqual(Luong.objects.get(tong_hop__nhan_vien=self.people[0]).tong_tien_thuong,0)
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
        response=self.post(self.hr,reverse('thuong:export'),{'thang':10,'nam':2026})
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

    def test_bonus_to_payroll_submission_approval_and_payment(self):
        from bang_luong.services.quy_trinh import gui_bang_luong, xu_ly_trang_thai_luong
        for i in range(2):
            self.approve_attendance(i)
        selected={'nhan_vien_ids':[p.pk for p in self.people]}
        self.post(self.hr,self.submit_url,selected)
        self.post(self.director,self.decision_url,{**selected,'action':'approve'})
        self.assertEqual(Luong.objects.filter(tong_tien_thuong=3200000).count(),2)
        gui_bang_luong(self.hr,self.period.pk)
        xu_ly_trang_thai_luong(self.director,self.period.pk,'approve','Đã kiểm tra')
        xu_ly_trang_thai_luong(self.director,self.period.pk,'paid','Đã chuyển khoản','Biên lai thử nghiệm')
        self.assertEqual(Luong.objects.filter(trang_thai='paid').count(),2)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse('bang_luong:list'),{'month':10,'year':2026}).status_code,200)
        self.client.force_login(self.people[0].nguoi_dung)
        phieu=Luong.objects.get(tong_hop__nhan_vien=self.people[0])
        self.assertEqual(self.client.get(reverse('bang_luong:detail',args=[phieu.pk])).status_code,200)
        self.assertEqual(self.client.get(reverse('home')).status_code,200)

    def test_database_rejects_inconsistent_total(self):
        bang=self.approve_attendance()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Thuong.objects.filter(pk=bang.pk).update(tong_thuong=1)
