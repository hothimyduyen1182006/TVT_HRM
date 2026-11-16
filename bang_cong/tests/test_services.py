from datetime import date, time
from decimal import Decimal
from io import StringIO
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from nhan_vien.models import NhanVien, PhongBan
from nghi_phep.models import LeaveDay
from ..models import ChamCong, KyCong, LichLamViec, NhatKyCong, LichSuTangCa
from ..services.chot_bang_cong_service import xu_ly_trang_thai_ky_cong
from django.core.management.base import CommandError


class AutomaticOvertimeTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.period.thang=10
        self.period.save()
        for day in range(1,32):
            value=date(2026,10,day)
            work=value.weekday()<5
            LichLamViec.objects.create(ngay=value,loai_ngay='work' if work else 'rest',cong_chuan=1 if work else 0)

    def record(self,**values):
        return AttendanceTests.record(self,ngay=date(2026,10,5),**values)

    def test_checkout_boundaries_for_all_departments(self):
        for employee in [self.emp,self.other]:
            for end,expected in [(time(16,30),0),(time(17),0),(time(17,30),Decimal('.5')),
                                 (time(18),1),(time(19),2),(time(20),3)]:
                with self.subTest(employee=employee.ma_ho_so,end=end):
                    row=ChamCong.objects.filter(nhan_vien=employee,ngay=date(2026,10,5)).first() or self.record(nhan_vien=employee)
                    row.gio_ra=end
                    luu_cham_cong(self.hr,row,'Kiểm thử tháng 10')
                    row.refresh_from_db()
                    self.assertEqual(row.gio_tang_ca,expected)
                    self.assertEqual(row.gio_ra,end)
                    self.assertLessEqual(row.so_gio_lam,8)
                    self.assertLessEqual(row.tong_cong,1)
        self.assertFalse(LichSuTangCa.objects.exists())

    def test_missing_checkout_invalid_status_and_late_arrival(self):
        row=self.record(gio_ra=None,trang_thai='incomplete')
        row.save()
        self.assertEqual(row.gio_tang_ca,0)
        row.trang_thai='absent'
        row.gio_vao=None
        row.gio_ra=time(20)
        self.assertEqual(row.gio_tang_ca,0)
        self.assertEqual(self.record(gio_vao=time(18),gio_ra=time(19)).gio_tang_ca,1)

    def test_hr_edit_changes_ot_and_audit_without_changing_history(self):
        row=luu_cham_cong(self.hr,self.record(gio_ra=time(19)),'Tạo công')
        history=LichSuTangCa.objects.bulk_create([LichSuTangCa(nhan_vien=self.emp,ngay=row.ngay,so_gio_duoc_duyet=9,he_so=3,trang_thai='pending')])[0]
        before=list(LichSuTangCa.objects.values())
        row.gio_ra=time(18)
        luu_cham_cong(self.hr,row,'Sửa giờ ra')
        self.assertEqual(row.gio_tang_ca,1)
        self.assertEqual(row.so_gio_lam,8)
        log=NhatKyCong.objects.filter(hanh_dong='edit_record').latest('pk')
        self.assertEqual(Decimal(log.du_lieu_cu['overtime_hours']),2)
        self.assertEqual(Decimal(log.du_lieu_moi['overtime_hours']),1)
        self.assertEqual(list(LichSuTangCa.objects.values()),before)
        for operation in [history.save,history.delete]:
            with self.assertRaises(PermissionDenied): operation()

    def test_old_urls_are_missing_for_every_role_and_method(self):
        row=luu_cham_cong(self.hr,self.record(gio_ra=time(19)),'Công thực tế')
        self.other_user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        before=list(ChamCong.objects.values())
        for actor in [self.user,self.other_user,self.hr,self.director]:
            client=Client(enforce_csrf_checks=True)
            client.force_login(actor)
            for action in ['submit','approve','reject']:
                for url in [f'/bang_cong/{row.pk}/overtime/{action}/',f'/bang_cong/overtime/{row.pk}/{action}/']:
                    self.assertEqual(client.get(url).status_code,404)
                    self.assertEqual(client.post(url,{'hours':'99'}).status_code,404)
        self.assertEqual(list(ChamCong.objects.values()),before)


    def test_personal_month_summary_includes_overtime(self):
        row = luu_cham_cong(self.hr, self.record(gio_ra=time(19)), 'Công thực tế')
        self.client.force_login(self.user)
        response = self.client.get('/bang_cong/ca-nhan/?month=10&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['summary']['ot'], 2)
        self.assertNotContains(response, 'OT tự động:')
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.emp.pk}/?month=10&year=2026').status_code, 404)
    def test_rest_holiday_and_night_are_handled_separately(self):
        from ..services.cham_cong_service import tinh_tang_ca_tu_dong,tong_hop_tang_ca_tinh_luong
        day=LichLamViec.objects.get(ngay=date(2026,10,5))
        row=self.record()
        for kind,rate in [('rest',2),('holiday',3)]:
            day.loai_ngay,day.cong_chuan=kind,0
            day.save()
            row=luu_cham_cong(self.hr,row,'Ngày đặc biệt')
            item=tinh_tang_ca_tu_dong(row,self.period,day)
            self.assertEqual(item['hours'],8)
            self.assertEqual(item['multiplier'],rate)
            self.assertEqual(row.tong_cong,0)
        row.gio_ra=time(23)
        luu_cham_cong(self.hr,row,'Giữ giờ ra ban đêm')
        self.assertEqual(row.gio_ra,time(23))
        with self.assertRaisesMessage(ValidationError,'ban đêm'): tong_hop_tang_ca_tinh_luong(self.emp,2026,10)
        row.gio_ra=time(2)
        with self.assertRaises(ValidationError): luu_cham_cong(self.hr,row,'Ca qua đêm chưa hỗ trợ')

    def test_locked_period_still_blocks_changes(self):
        row=luu_cham_cong(self.hr,self.record(gio_ra=time(19)),'Công thực tế')
        self.period.trang_thai='approved'
        self.period.save()
        row.gio_ra=time(20)
        with self.assertRaises(ValidationError): luu_cham_cong(self.hr,row,'Không vượt khóa')
        row.refresh_from_db()
        self.assertEqual(row.gio_ra,time(19))

    def test_checkout_punch_immediately_exposes_ot_without_creating_request(self):
        from datetime import datetime
        from unittest.mock import patch
        from ..services.cham_cong_service import ghi_nhan_cham_cong
        with patch('bang_cong.services.cham_cong_service.timezone.localtime',return_value=datetime(2026,10,5,8)):
            ghi_nhan_cham_cong(self.user,'in')
        with patch('bang_cong.services.cham_cong_service.timezone.localtime',return_value=datetime(2026,10,5,18,30)):
            row=ghi_nhan_cham_cong(self.user,'out')
        row.refresh_from_db()
        self.assertEqual(row.gio_tang_ca,Decimal('1.5'))
        self.assertEqual(row.gio_ra,time(18,30))
        self.assertEqual(row.tong_cong,1)
        self.assertFalse(LichSuTangCa.objects.exists())

    def test_pending_historical_requests_no_longer_block_attendance_approval(self):
        from ..services.chot_bang_cong_service import duyet_cong_nhan_vien
        for day in LichLamViec.objects.filter(ngay__month=10,loai_ngay='work'):
            luu_cham_cong(self.hr,AttendanceTests.record(self,ngay=day.ngay),'Công tháng 10')
        LichSuTangCa.objects.bulk_create([LichSuTangCa(nhan_vien=self.emp,ngay=date(2026,10,5),
            so_gio_duoc_duyet=2,he_so=Decimal('1.5'),trang_thai='pending')])
        before=list(LichSuTangCa.objects.values())
        duyet_cong_nhan_vien(self.hr,self.emp,self.period.pk)
        self.assertTrue(self.period.employee_approvals.filter(nhan_vien=self.emp).exists())
        self.assertEqual(list(LichSuTangCa.objects.values()),before)


class AttendanceTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user('hr')
        self.hr.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        self.director = User.objects.create_user('director')
        self.director.groups.add(Group.objects.get_or_create(name='Giám đốc')[0])
        self.user = User.objects.create_user('employee')
        self.other_user = User.objects.create_user('other')
        self.dep = PhongBan.objects.create(ma_phong_ban='A', ten_phong_ban='Phòng A')
        self.other_dep = PhongBan.objects.create(ma_phong_ban='B', ten_phong_ban='Phòng B')
        self.emp = NhanVien.objects.create(ma_ho_so='NV01', ho_va_ten='Nhân viên 1', nguoi_dung=self.user,
                    phong_ban=self.dep, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=Decimal('22000000'))
        self.other = NhanVien.objects.create(ma_ho_so='NV02', ho_va_ten='Nhân viên 2', nguoi_dung=self.other_user,
                    phong_ban=self.other_dep, ngay_vao_lam=date(2020, 1, 1), luong_co_ban=Decimal('22000000'))
        self.period = KyCong.objects.create(thang=1, nam=2026, gio_bat_dau=time(8),
                 bat_dau_nghi_trua=time(12), ket_thuc_nghi_trua=time(13), gio_ket_thuc=time(17), gio_chuan=8)
        for day in range(1, 32):
            value = date(2026, 1, day)
            work = value.weekday() < 5
            LichLamViec.objects.create(ngay=value, loai_ngay='work' if work else 'rest', cong_chuan=1 if work else 0)

    def record(self, employee=None, **kwargs):
        values = dict(nhan_vien=employee or self.emp, ngay=date(2026, 1, 5),
                      gio_vao=time(8), gio_ra=time(17), trang_thai='present')
        values.update(kwargs)
        return ChamCong(**values)

    def test_lunch_and_regular_hours(self):
        row = luu_cham_cong(self.hr, self.record(), 'Kiểm tra')
        self.assertEqual(row.so_gio_lam, 8)
        self.assertEqual(row.tong_cong, 1)
        self.assertEqual(NhatKyCong.objects.count(), 1)

    def test_late_and_half_day(self):
        row = luu_cham_cong(self.hr, self.record(gio_vao=time(9)), 'Đi muộn')
        self.assertEqual(row.so_phut_tre, 60)
        self.assertEqual(row.tong_cong, Decimal('.875'))
        row.gio_vao, row.gio_ra = time(8), time(12)
        luu_cham_cong(self.hr, row, 'Nửa ngày')
        self.assertEqual(row.cong_thuc_te, Decimal('.5'))

    def test_after_hours_does_not_double_normal_work(self):
        row = luu_cham_cong(self.hr, self.record(gio_ra=time(20)), 'Kiểm tra')
        self.assertEqual(row.so_gio_lam, 8)
        self.assertEqual(row.cong_thuc_te, 1)

    def test_invalid_checkout(self):
        for out in [time(7), time(8)]:
            with self.assertRaises(ValidationError):
                luu_cham_cong(self.hr, self.record(gio_ra=out), 'Sai giờ')

    def test_duplicate_database_constraint(self):
        luu_cham_cong(self.hr, self.record(), 'Lần 1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ChamCong.objects.create(nhan_vien=self.emp, ngay=date(2026, 1, 5), trang_thai='absent')

    def test_paid_and_unpaid_leave(self):
        leave = LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 5), units=1, paid=True,
                                        reason='Phép', approved=True)
        row = luu_cham_cong(self.hr, self.record(gio_vao=None, gio_ra=None, trang_thai='leave'), 'Phép')
        self.assertEqual(row.tong_cong, 1)
        self.assertEqual(row.cong_thuc_te, 0)
        leave.paid = False
        leave.save()
        luu_cham_cong(self.hr, row, 'Không lương')
        self.assertEqual(row.tong_cong, 0)

    def test_overlap_rejected(self):
        LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 5), units=1, paid=True,
                                reason='Phép', approved=True)
        with self.assertRaises(ValidationError):
            luu_cham_cong(self.hr, self.record(), 'Trùng')

    def test_ordinary_user_cannot_edit(self):
        with self.assertRaises(PermissionDenied):
            luu_cham_cong(self.user, self.record(), 'Không có quyền')

    def test_locked_period(self):
        self.period.trang_thai = 'approved'
        self.period.save()
        with self.assertRaises(ValidationError):
            luu_cham_cong(self.hr, self.record(), 'Kỳ khóa')

    def test_approval_requires_complete_data(self):
        with self.assertRaises(ValidationError):
            xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'approve', 'Thiếu công')

    def test_approved_attendance_blocks_new_records(self):
        from ..models import ChotBangCong
        row = luu_cham_cong(self.hr, self.record(), 'Tạo công')
        for lock in ['period', 'employee']:
            if lock == 'period':
                self.period.trang_thai = 'approved'
                self.period.save()
            else:
                self.period.trang_thai = 'pending'
                self.period.save()
                ChotBangCong.objects.create(ky_cong=self.period, nhan_vien=self.emp,
                                                          nguoi_duyet=self.director)
            for actor in [self.hr, self.director]:
                with self.subTest(lock=lock, actor=actor.username):
                    self.client.force_login(actor)
                    new_day = 6 if actor == self.hr else 7
                    response = self.client.post('/bang_cong/them/', {
                        'employee': self.emp.pk, 'date': f'2026-01-{new_day:02}', 'check_in': '08:00',
                        'check_out': '17:00', 'status': 'present', 'reason': 'Tạo thêm'})
                    if lock == 'period':
                        self.assertEqual(response.status_code, 200)
                        self.assertContains(response, 'Kỳ công đã duyệt, cần mở lại trước.')
                        self.assertFalse(ChamCong.objects.filter(nhan_vien=self.emp,
                                                                        ngay=date(2026, 1, new_day)).exists())
                    else:
                        # Quy tắc của bản 616e798: chỉ khóa bản ghi đã có khi duyệt nhân viên.
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(ChamCong.objects.filter(nhan_vien=self.emp,
                                                                       ngay=date(2026, 1, new_day)).exists())

    def test_self_and_department_scopes(self):
        own = luu_cham_cong(self.hr, self.record(), 'Công')
        other = luu_cham_cong(self.hr, self.record(nhan_vien=self.other), 'Công')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.emp.pk}/?month=1&year=2026').status_code, 200)
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.other.pk}/?month=1&year=2026').status_code, 404)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.truong_phong = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.other.pk}/?month=1&year=2026').status_code, 404)

    def test_lists_and_create(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/bang_cong/?month=1&year=2026').status_code, 200)
        response = self.client.get('/bang_cong/?month=13&year=2026')
        self.assertTrue(response.context['form'].errors)
        response = self.client.post('/bang_cong/them/', {'employee': self.emp.pk, 'date': '2026-01-05',
            'check_in': '08:00', 'check_out': '17:00', 'status': 'present', 'note': '', 'reason': 'Tạo'})
        self.assertEqual(response.status_code, 302)

    def test_full_month_approval_and_audit(self):
        for employee in [self.emp, self.other]:
            for day in LichLamViec.objects.filter(loai_ngay='work'):
                luu_cham_cong(self.hr, self.record(nhan_vien=employee, ngay=day.ngay), 'Kiểm tra ngày')
        xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'approve', 'Đủ dữ liệu')
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'approved')
        self.assertEqual(set(self.period.ds_nhan_vien), {self.emp.pk, self.other.pk})
        xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'reopen', 'Cần kiểm tra lại')
        self.period.refresh_from_db()
        self.assertEqual(self.period.phien_ban, 2)

    def test_calendar_command_does_not_overwrite(self):
        from django.core.management import call_command, CommandError
        from io import StringIO
        call_command('create_calendar', year=2026, month=2, workdays='0,1,2,3,4', holidays='2026-02-02', stdout=StringIO())
        self.assertEqual(LichLamViec.objects.get(ngay=date(2026, 2, 2)).loai_ngay, 'holiday')
        with self.assertRaises(CommandError):
            call_command('create_calendar', year=2026, month=2, workdays='0,1,2,3,4')

    def test_dashboard_and_employees(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertRedirects(self.client.get('/dashboard/'), '/bang_cong/', fetch_redirect_response=False)
        response = self.client.get('/nhan_vien/')
        self.assertEqual(response.status_code, 403)
        response = self.client.get('/nhan_vien/me/')
        self.assertContains(response, 'NV01')
        self.assertNotContains(response, 'NV02')

    def test_monthly_summary_groups_employee_and_filters(self):
        luu_cham_cong(self.hr, self.record(), 'Ngày 1')
        luu_cham_cong(self.hr, self.record(ngay=date(2026, 1, 6), gio_vao=time(9)), 'Ngày 2')
        luu_cham_cong(self.hr, self.record(nhan_vien=self.other), 'Phòng khác')
        self.client.force_login(self.hr)
        response = self.client.get('/bang_cong/', {'month': 1, 'year': 2026, 'q': 'NV01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 1)
        row = response.context['rows'][0]
        self.assertEqual(row['paid'], Decimal('1.875'))
        self.assertEqual(row['late_count'], 1)
        self.assertEqual(row['late'], 60)
        self.assertContains(response, 'BẢNG CÔNG TỔNG HỢP')
        response = self.client.get('/bang_cong/', {'month': 1, 'year': 2026, 'department': self.dep.pk})
        self.assertEqual(len(response.context['rows']), 1)

    def test_personal_month_and_missing_days(self):
        luu_cham_cong(self.hr, self.record(), 'Ngày đủ giờ')
        self.client.force_login(self.user)
        response = self.client.get('/bang_cong/', {'month': 1, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'BẢNG CHẤM CÔNG CỦA')
        self.assertEqual(response.context['average'], '8:00')
        rows = response.context['rows']
        self.assertEqual(next(r for r in rows if r['date'] == date(2026, 1, 3))['state'], 'rest')
        self.assertEqual(next(r for r in rows if r['date'] == date(2026, 1, 6))['state'], 'incomplete')
        self.assertFalse(response.context['can_edit'])
        self.assertEqual(response.context['summary']['absent'], 0)

    def test_month_detail_filters_and_pagination(self):
        luu_cham_cong(self.hr, self.record(gio_vao=time(9)), 'Đi muộn')
        self.client.force_login(self.hr)
        url = f'/bang_cong/nhan-vien/{self.emp.pk}/'
        response = self.client.get(url, {'month': 1, 'year': 2026, 'state': 'late'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 1)
        self.assertContains(response, 'Đi làm trễ')
        response = self.client.get(url, {'month': 1, 'year': 2026, 'start': '2026-01-10', 'end': '2026-01-02'})
        self.assertTrue(response.context['form'].errors)
        response = self.client.get(url, {'month': 1, 'year': 2026, 'page': 2})
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_new_pages_enforce_department_scope(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.other.pk}/').status_code, 404)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.truong_phong = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/bang_cong/nhan-vien/{self.other.pk}/').status_code, 404)

    def test_shared_navigation_on_application_and_admin_pages(self):
        root = User.objects.create_user('navigation-root', is_superuser=True, is_staff=True)
        self.client.force_login(root)
        pages = [('/', None), ('/dashboard/', 'DASHBOARD'), ('/nhan_vien/', 'NHÂN VIÊN'),
                 ('/bang_cong/', 'BẢNG CÔNG'), ('/bang_luong/', 'BẢNG LƯƠNG'),
                 ('/bang_luong/inputs/', 'NHÂN VIÊN'), ('/admin/bonuses/bonus/', 'BẢNG THƯỞNG'),
                 ('/admin/leaves/leaveday/', 'NGHỈ PHÉP'), ('/admin/', None)]
        for url, active in pages:
            with self.subTest(url=url):
                response = self.client.get(url, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'aria-label="Điều hướng chính"', count=1)
                self.assertContains(response, 'css/navigation.css')
                if active:
                    self.assertContains(response, f'aria-current="page">{active}</a>')
        self.client.logout()
        response = self.client.get('/accounts/login/')
        self.assertNotContains(response, 'aria-label="Điều hướng chính"')
        self.assertNotContains(response, 'aria-label="Tài khoản"')

    def test_employee_approval_button_is_below_attendance(self):
        self.client.force_login(self.hr)
        response = self.client.get('/bang_cong/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        response = self.client.get(f'/bang_cong/nhan-vien/{self.emp.pk}/?month=1&year=2026')
        url = f'/bang_cong/nhan-vien/{self.emp.pk}/duyet/{self.period.pk}/'
        self.assertContains(response, f'action="{url}"', count=1)
        html = response.content.decode()
        self.assertLess(html.index('</table>'), html.index('class="at-approval-footer"'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_approval_post_validates_data_and_records_actor(self):
        from ..models import ChotBangCong
        self.client.force_login(self.hr)
        url = f'/bang_cong/nhan-vien/{self.emp.pk}/duyet/{self.period.pk}/'
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'còn thiếu ngày')
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'pending')
        for day in LichLamViec.objects.filter(loai_ngay='work'):
            luu_cham_cong(self.hr, self.record(ngay=day.ngay), 'Đối chiếu')
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'Đã duyệt bảng công của')
        self.assertNotContains(response, f'action="{url}"')
        self.assertContains(response, 'disabled>Đã duyệt</button>')
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'pending')
        self.assertEqual(ChotBangCong.objects.get(nhan_vien=self.emp).nguoi_duyet, self.hr)
        self.assertFalse(ChotBangCong.objects.filter(nhan_vien=self.other).exists())
        self.assertTrue(NhatKyCong.objects.filter(nguoi_thuc_hien=self.hr, hanh_dong='approve_employee').exists())
        response = self.client.get('/bang_cong/?month=1&year=2026')
        states = {r['employee'].pk: r['state'] for r in response.context['rows']}
        self.assertEqual(states[self.emp.pk], 'approved')
        self.assertEqual(states[self.other.pk], 'empty')
        row = ChamCong.objects.filter(nhan_vien=self.emp).first()
        with self.assertRaises(ValidationError):
            luu_cham_cong(self.hr, row, 'Không sửa công đã duyệt riêng')
        for day in LichLamViec.objects.filter(loai_ngay='work'):
            luu_cham_cong(self.hr, self.record(nhan_vien=self.other, ngay=day.ngay), 'Đối chiếu')
        self.client.post(f'/bang_cong/nhan-vien/{self.other.pk}/duyet/{self.period.pk}/')
        self.period.refresh_from_db()
        self.assertEqual(self.period.trang_thai, 'approved')
        self.assertEqual(set(self.period.ds_nhan_vien), {self.emp.pk, self.other.pk})

    def test_approved_payroll_blocks_reopen_button_and_service(self):
        from bang_luong.models import PayrollPeriod
        self.period.trang_thai = 'approved'
        self.period.save()
        PayrollPeriod.objects.create(attendance_period=self.period, status='approved')
        self.client.force_login(self.director)
        response = self.client.get('/bang_cong/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        self.assertNotContains(response, 'name="action" value="reopen"')
        with self.assertRaises(ValidationError):
            xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'reopen', 'Không vượt khóa lương')

from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from django.test import TestCase
from ..models import ChamCong, NhatKyCong, ChotBangCong, KyCong, LichLamViec
from ..services.cham_cong_service import ghi_nhan_cham_cong


class ClockTests(TestCase):
    setUp = AttendanceTests.setUp
    def at(self, hour, minute=0):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 1, 5, hour, minute, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_punch_lifecycle(self):
        with self.at(8):
            row = ghi_nhan_cham_cong(self.user, 'in')
            self.assertEqual(row.trang_thai, 'incomplete')
            self.assertEqual(row.tong_cong, 0)
            with self.assertRaises(ValidationError):
                ghi_nhan_cham_cong(self.user, 'in')
        with self.at(17):
            row = ghi_nhan_cham_cong(self.user, 'out')
            self.assertEqual(row.so_gio_lam, 8)
            self.assertEqual(row.tong_cong, 1)
            with self.assertRaises(ValidationError):
                ghi_nhan_cham_cong(self.user, 'out')
        self.assertFalse(NhatKyCong.objects.exists())

    def test_late_checkout_does_not_submit_or_approve_ot(self):
        from ..models import LichSuTangCa
        with self.at(8):
            ghi_nhan_cham_cong(self.user, 'in')
        with self.at(19):
            row = ghi_nhan_cham_cong(self.user, 'out')
        self.assertEqual(row.gio_ra, time(19))
        self.assertEqual(row.so_gio_lam, 8)
        self.assertFalse(LichSuTangCa.objects.exists())

    def test_out_without_in_and_approved_lock(self):
        with self.at(9):
            with self.assertRaises(ValidationError):
                ghi_nhan_cham_cong(self.user, 'out')
            ChamCong.objects.create(nhan_vien=self.emp, ngay=date(2026,1,5),
                gio_vao=time(8), gio_ra=time(17), trang_thai='present', nguoi_cap_nhat=self.hr)
            ChotBangCong.objects.create(ky_cong=self.period, nhan_vien=self.emp, nguoi_duyet=self.hr)
            with self.assertRaises(ValidationError):
                ghi_nhan_cham_cong(self.user, 'in')

    def test_view_uses_own_employee_and_server_time(self):
        self.client.force_login(self.user)
        url = reverse('bang_cong:cham-cong')
        with self.at(8, 15):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(ChamCong.objects.exists())
            self.client.post(url, {'action': 'in', 'employee': self.other.pk, 'check_in': '07:00'})
            row = ChamCong.objects.get()
            self.assertEqual(row.nhan_vien, self.emp)
            self.assertEqual(row.gio_vao, time(8, 15))
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['thao_tac_thanh_cong'], 'in')
            self.assertEqual(response.context['trang_thai_trang'], 'dang_trong_ca')
            self.assertTrue(response.context['co_the_ket_thuc_ca'])
        with self.at(17):
            self.client.post(url, {'action': 'out'})
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['thao_tac_thanh_cong'], 'out')
            self.assertEqual(response.context['trang_thai_trang'], 'da_hoan_tat')
            self.assertFalse(response.context['co_the_ket_thuc_ca'])

    def test_unlinked_user_denied(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse('bang_cong:cham-cong')).status_code, 403)

    def test_invalid_shift_blocks_punch_even_with_old_confirmation(self):
        for values in [{'gio_chuan': 0}, {'gio_chuan': -1}, {'ket_thuc_nghi_trua': time(11)}]:
            with self.subTest(values=values):
                KyCong.objects.filter(pk=self.period.pk).update(gio_chuan=8, ket_thuc_nghi_trua=time(13))
                KyCong.objects.filter(pk=self.period.pk).update(**values)
                with self.at(8), self.assertRaises(ValidationError):
                    ghi_nhan_cham_cong(self.user, 'in')
                self.assertFalse(ChamCong.objects.exists())

    def test_incomplete_or_invalid_calendar_blocks_punch(self):
        LichLamViec.objects.filter(ngay=date(2026,1,31)).delete()
        with self.at(8), self.assertRaises(ValidationError):
            ghi_nhan_cham_cong(self.user, 'in')
        LichLamViec.objects.create(ngay=date(2026,1,31),loai_ngay='rest',cong_chuan=1)
        with self.at(8), self.assertRaises(ValidationError):
            ghi_nhan_cham_cong(self.user, 'in')
        self.assertFalse(ChamCong.objects.exists())

    def test_valid_period_can_be_approved_without_confirmation(self):
        from ..services.chot_bang_cong_service import duyet_cong_nhan_vien
        for day in LichLamViec.objects.filter(loai_ngay='work'):
            AttendanceTests.record(self, ngay=day.ngay, nguoi_cap_nhat=self.hr).save()
        approval = duyet_cong_nhan_vien(self.hr, self.emp, self.period.pk)
        self.assertEqual(approval.nhan_vien_id, self.emp.pk)
        self.period.refresh_from_db()
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])


class AutomaticMonthClockTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.period.thang = 10
        self.period.save()
        LichLamViec.objects.all().delete()
        for number in range(1, 32):
            day = date(2026, 10, number)
            work = day.weekday() < 5
            LichLamViec.objects.create(ngay=day, loai_ngay='work' if work else 'rest', cong_chuan=1 if work else 0)
        self.client.force_login(self.user)

    def at(self, number=11, hour=8):
        return patch('django.utils.timezone.localtime', return_value=datetime(2026, 11, number, hour,
            tzinfo=ZoneInfo('Asia/Ho_Chi_Minh')))

    def test_get_previews_inherited_shift_without_writing(self):
        with self.at():
            response = self.client.get(reverse('bang_cong:cham-cong'))
        self.assertTrue(response.context['co_the_vao_ca'])
        self.assertEqual(response.context['ky_cong'].gio_bat_dau, time(8))
        self.assertIsNone(response.context['ky_cong'].pk)
        self.assertContains(response, 'value="in"')
        self.assertEqual(KyCong.objects.count(), 1)
        self.assertEqual(LichLamViec.objects.count(), 31)
        self.assertFalse(ChamCong.objects.exists())
        self.assertFalse(NhatKyCong.objects.exists())

    def test_successful_checkin_opens_one_period_and_preserves_source(self):
        before = list(LichLamViec.objects.order_by('ngay').values())
        source = KyCong.objects.values().get(pk=self.period.pk)
        with self.at():
            response = self.client.post(reverse('bang_cong:cham-cong'), {'action':'in','employee':self.other.pk,'check_in':'06:00'})
            self.assertEqual(response.status_code, 302)
            row = ChamCong.objects.get(nhan_vien=self.emp)
            self.assertEqual(row.gio_vao, time(8))
            self.assertEqual(row.ngay, date(2026, 11, 11))
            ghi_nhan_cham_cong(self.other_user, 'in')
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user, 'in')
        period = KyCong.objects.get(nam=2026, thang=11)
        self.assertEqual(period.trang_thai, 'pending')
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])
        self.assertEqual(period.ds_nhan_vien, [])
        self.assertFalse(period.employee_approvals.exists())
        self.assertEqual(KyCong.objects.count(), 2)
        self.assertEqual(LichLamViec.objects.filter(ngay__year=2026,ngay__month=11).count(), 30)
        self.assertEqual(NhatKyCong.objects.filter(hanh_dong='auto_open_period').count(), 1)
        self.assertEqual(before, list(LichLamViec.objects.filter(ngay__month=10).order_by('ngay').values()))
        self.assertEqual(source, KyCong.objects.values().get(pk=self.period.pk))
        with self.at(hour=17):
            row = ghi_nhan_cham_cong(self.user, 'out')
            self.assertEqual(row.so_gio_lam, 8)
            self.assertEqual(row.tong_cong, 1)
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user, 'out')

    def test_failed_checkout_and_invalid_action_roll_back_initialization(self):
        with self.at():
            for action in ['out','invalid']:
                with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user, action)
        self.assertEqual(KyCong.objects.count(), 1)
        self.assertEqual(LichLamViec.objects.count(), 31)
        self.assertFalse(NhatKyCong.objects.exists())

    def test_weekly_rest_does_not_open_period_or_allow_punch(self):
        with self.at(number=14):
            response = self.client.get(reverse('bang_cong:cham-cong'))
            self.assertFalse(response.context['co_the_vao_ca'])
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user, 'in')
        self.assertEqual(KyCong.objects.count(), 1)

    def test_explicit_holiday_is_kept_when_month_is_opened(self):
        holiday = LichLamViec.objects.create(ngay=date(2026,11,13),loai_ngay='holiday',cong_chuan=0,ghi_chu='Ngày nghỉ đã cấu hình')
        before = LichLamViec.objects.values().get(pk=holiday.pk)
        with self.at(): ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(before, LichLamViec.objects.values().get(pk=holiday.pk))
        with self.at(number=13):
            response = self.client.get(reverse('bang_cong:cham-cong'))
            self.assertFalse(response.context['co_the_vao_ca'])
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.other_user,'in')

    def test_valid_source_is_used_without_manual_confirmation(self):
        self.period.save()
        with self.at():
            response = self.client.get(reverse('bang_cong:cham-cong'))
            self.assertTrue(response.context['co_the_vao_ca'])
            ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(KyCong.objects.count(),2)

    def test_future_policy_is_not_applied_before_its_month(self):
        KyCong.objects.create(nam=2026,thang=12,gio_bat_dau=time(9),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(18),gio_chuan=8)
        with self.at(): ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(KyCong.objects.get(nam=2026,thang=11).gio_bat_dau,time(8))

    def test_leap_year_month_is_initialized_with_correct_day_count(self):
        with patch('django.utils.timezone.localtime',return_value=datetime(2028,2,14,8,
                   tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))):
            ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(LichLamViec.objects.filter(ngay__year=2028,ngay__month=2).count(),29)
        self.assertTrue(LichLamViec.objects.filter(ngay=date(2028,2,29)).exists())

    def test_partial_source_calendar_is_not_used(self):
        LichLamViec.objects.filter(ngay=date(2026,10,31)).delete()
        with self.at():
            with self.assertRaisesMessage(ValidationError,'chưa đủ tháng'): ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(KyCong.objects.count(),1)

    def test_irregular_weekly_calendar_is_not_silently_inferred(self):
        LichLamViec.objects.filter(ngay=date(2026,10,7)).update(loai_ngay='rest',cong_chuan=0)
        with self.at():
            with self.assertRaisesMessage(ValidationError,'ngoại lệ'): ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(KyCong.objects.count(),1)

    def test_existing_valid_shift_is_kept_without_confirmation(self):
        period = KyCong.objects.create(nam=2026,thang=11,gio_bat_dau=time(9),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(18),gio_chuan=8)
        with self.at():
            ghi_nhan_cham_cong(self.user,'in')
        period.refresh_from_db()
        self.assertNotIn('policy_confirmed', [field.name for field in KyCong._meta.fields])
        self.assertEqual(period.gio_bat_dau,time(9))
        self.assertEqual(LichLamViec.objects.filter(ngay__month=11).count(),30)

    def test_source_approval_is_not_copied_and_new_month_can_still_be_locked(self):
        self.period.trang_thai='approved'
        self.period.save()
        ChotBangCong.objects.create(ky_cong=self.period,nhan_vien=self.emp,nguoi_duyet=self.hr)
        with self.at(): ghi_nhan_cham_cong(self.user,'in')
        period=KyCong.objects.get(thang=11,nam=2026)
        self.assertEqual(period.trang_thai,'pending')
        self.assertFalse(period.employee_approvals.exists())
        period.trang_thai='approved'
        period.save()
        with self.at(hour=17):
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user,'out')
        self.assertIsNone(ChamCong.objects.get(nhan_vien=self.emp,ngay=date(2026,11,11)).gio_ra)

    def test_authentication_csrf_and_hire_date_do_not_create_calendar(self):
        from django.test import Client
        url=reverse('bang_cong:cham-cong')
        anonymous=Client()
        self.assertEqual(anonymous.post(url,{'action':'in'}).status_code,302)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(url,{'action':'in'}).status_code,403)
        with self.at():
            with self.assertRaises(PermissionDenied): ghi_nhan_cham_cong(AnonymousUser(),'in')
            self.emp.ngay_vao_lam=date(2026,12,1)
            self.emp.save()
            with self.assertRaises(ValidationError): ghi_nhan_cham_cong(self.user,'in')
        self.assertEqual(KyCong.objects.count(),1)
        self.assertFalse(ChamCong.objects.exists())

from datetime import date, time
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from . import test_permissions
from ..models import ChamCong


class MonthPeriodTests(TestCase):
    setUp = test_permissions.BulkApprovalTests.setUp

    def test_summary_skips_ot_while_detail_and_saved_summary_keep_it(self):
        from ..services.tong_hop_service import cap_nhat_tong_hop
        from ..services.cham_cong_service import tinh_tang_ca_tu_dong
        employee = self.employees[0]
        ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 11, 10),
                                gio_vao=time(8), gio_ra=time(19), trang_thai='present')
        with patch('bang_cong.services.tong_hop_service.tinh_tang_ca_tu_dong', wraps=tinh_tang_ca_tu_dong) as overtime:
            response = self.client.get('/bang_cong/?month=11&year=2026')
            self.assertEqual(response.status_code, 200)
            overtime.assert_not_called()
            self.assertNotContains(response, 'OT:')
            self.assertTrue(all('ot' not in row for row in response.context['rows']))
            response = self.client.get(f'/bang_cong/nhan-vien/{employee.pk}/?month=11&year=2026')
            self.assertEqual(response.context['summary']['ot'], Decimal(2))
            self.assertEqual(overtime.call_count, 1)
        summary = cap_nhat_tong_hop(employee, self.period)
        self.assertEqual(summary.gio_tang_ca, Decimal(2))

    def test_month_uses_summary_period_and_ignores_old_daily_filters(self):
        employee = self.employees[0]
        ChamCong.objects.create(nhan_vien=employee, ngay=date(2026, 11, 10),
                                gio_vao=time(9), gio_ra=time(17), trang_thai='present')
        url = f'/bang_cong/nhan-vien/{employee.pk}/'
        response = self.client.get(url, {
            'month': 11, 'year': 2026, 'state': 'invalid', 'start': 'bad', 'end': 'bad',
            'day': 'bad', 'department': 'bad', 'q': 'unrelated', 'page': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(response.context['month_query'], 'month=11&year=2026')
        self.assertEqual(response.context['page_query'], 'month=11&year=2026')
        self.assertNotContains(response, '&amp;state=')
        self.assertNotContains(response, 'at-stat-filter')
        self.assertNotContains(response, 'class="at-filter"')
        summary = self.client.get('/bang_cong/?month=11&year=2026')
        self.assertContains(summary, url + '?month=11&year=2026')

    def test_personal_month_shows_full_month(self):
        employee = self.employees[0]
        query = {'month': 11, 'year': 2026}
        self.client.force_login(employee.user)
        response = self.client.get('/bang_cong/ca-nhan/', query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)
        self.assertNotContains(response, 'class="at-filter"')

    def test_invalid_period_uses_default_month(self):
        employee = self.employees[0]
        query = {'month': 13, 'year': 2026}
        response = self.client.get(f'/bang_cong/nhan-vien/{employee.pk}/', query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 30)

from datetime import date, time
from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from ..models import (
    NhatKyCong, ChamCong, ChotBangCong, TongHopCong, LichLamViec,
)
from ..services.tong_hop_service import tong_hop_dung_tinh_luong
from ..services.chot_bang_cong_service import duyet_cong_nhan_vien, xu_ly_trang_thai_ky_cong, luu_cham_cong


class MonthlySummaryTests(TestCase):
    setUp = AttendanceTests.setUp

    def record(self, **values):
        return AttendanceTests.record(self, **values)

    def fill_month(self, employee):
        ChamCong.objects.bulk_create([
            self.record(nhan_vien=employee, ngay=day.ngay, nguoi_cap_nhat=self.hr)
            for day in LichLamViec.objects.filter(loai_ngay='work')
        ])

    def test_repeated_save_updates_one_summary_without_adding_ot_twice(self):
        row = luu_cham_cong(self.hr, self.record(gio_ra=time(19)), 'Create')
        summary = TongHopCong.objects.get(nhan_vien=self.emp, ky_cong=self.period)
        self.assertEqual((summary.tong_cong, summary.so_gio_lam, summary.gio_tang_ca), (1, 8, 2))
        self.assertEqual(row.so_gio_tang_ca, 2)
        audit_count = NhatKyCong.objects.count()
        luu_cham_cong(self.hr, row, 'No changes')
        summary.refresh_from_db()
        self.assertEqual(summary.gio_tang_ca, 2)
        self.assertEqual(TongHopCong.objects.count(), 1)
        self.assertEqual(NhatKyCong.objects.count(), audit_count)

    def test_views_and_payroll_comparison_do_not_create_summaries(self):
        self.record(nguoi_cap_nhat=self.hr).save()
        self.client.force_login(self.hr)
        response = self.client.get(reverse('bang_cong:cong-nhan-vien', args=[self.emp.pk]),
                                   {'month': 1, 'year': 2026})
        self.assertEqual(response.status_code, 200)
        summary = tong_hop_dung_tinh_luong(self.emp, self.period)
        self.assertIsNone(summary.pk)
        self.assertFalse(TongHopCong.objects.exists())

    def test_approval_links_summary_and_keeps_record_lock(self):
        self.fill_month(self.emp)
        approval = duyet_cong_nhan_vien(self.hr, self.emp, self.period.pk)
        approval.refresh_from_db()
        self.assertEqual(approval.tong_hop.nhan_vien_id, self.emp.pk)
        self.assertEqual(approval.tong_hop.trang_thai, 'approved')
        with self.assertRaises(ValidationError):
            duyet_cong_nhan_vien(self.hr, self.emp, self.period.pk)
        row = ChamCong.objects.filter(nhan_vien=self.emp).first()
        row.gio_ra = time(19)
        with self.assertRaises(ValidationError):
            luu_cham_cong(self.hr, row, 'Blocked')
        self.assertEqual(ChotBangCong.objects.count(), 1)

    def test_period_reopen_updates_summary_without_creating_extra_approvals(self):
        for employee in [self.emp, self.other]:
            self.fill_month(employee)
        xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'approve', 'Close')
        self.assertEqual(TongHopCong.objects.filter(trang_thai='approved').count(), 2)
        self.assertFalse(ChotBangCong.objects.filter(tong_hop__isnull=True).exists())
        xu_ly_trang_thai_ky_cong(self.director, self.period.pk, 'reopen', 'Reopen')
        self.assertEqual(TongHopCong.objects.filter(trang_thai='pending').count(), 2)
        self.assertFalse(ChotBangCong.objects.exists())


class AttendanceSchemaMigrationTests(TransactionTestCase):
    migrate_from = [('attendance', '0007_remove_policy_confirmed')]
    migrate_to = [('attendance', '0008_attendance_summary_and_adjustments')]

    def test_existing_data_is_transferred_and_backfill_is_idempotent(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('employees', '0005_shared_salary_settings'), *self.migrate_from])
        apps = executor.loader.project_state(self.migrate_from).apps
        try:
            User = apps.get_model('auth', 'User')
            NhanVien = apps.get_model('employees', 'Employee')
            PhongBan = apps.get_model('employees', 'Department')
            Period = apps.get_model('attendance', 'AttendancePeriod')
            Record = apps.get_model('attendance', 'AttendanceRecord')
            Audit = apps.get_model('attendance', 'AttendanceAuditLog')
            Approval = apps.get_model('attendance', 'EmployeeAttendanceApproval')
            Day = apps.get_model('attendance', 'WorkCalendarDay')
            user = User.objects.create(username='migration-user')
            department = PhongBan.objects.create(code='MIG', name='Migration')
            employee = NhanVien.objects.create(user_id=user.pk, code='MIG-01', full_name='Migration',
                department_id=department.pk, hire_date=date(2020, 1, 1), base_salary=10000000)
            period = Period.objects.create(year=2026, month=10, start_time=time(8), lunch_start=time(12),
                lunch_end=time(13), end_time=time(17), standard_hours=8, status='approved')
            Day.objects.create(date=date(2026,10,5), kind='work', expected_units=1)
            row = Record.objects.create(employee_id=employee.pk, date=date(2026,10,5), check_in=time(8),
                check_out=time(19), status='present', work_hours=8, actual_units=1, paid_units=1, updated_by_id=user.pk)
            approval = Approval.objects.create(period_id=period.pk, employee_id=employee.pk, approved_by_id=user.pk)
            audit = Audit.objects.create(actor_id=user.pk, action='edit_record', reason='Historical change',
                before={'check_out':'17:00:00'}, after={'pk':str(row.pk), 'check_out':'19:00:00'})
            before = Record.objects.values().get(pk=row.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            Record = new_apps.get_model('attendance', 'AttendanceRecord')
            Summary = new_apps.get_model('attendance', 'MonthlyAttendanceSummary')
            Adjustment = new_apps.get_model('attendance', 'AttendanceAdjustment')
            Approval = new_apps.get_model('attendance', 'EmployeeAttendanceApproval')
            current = Record.objects.values().get(pk=row.pk)
            self.assertEqual(before, {key:current[key] for key in before})
            self.assertEqual(current['recorded_overtime_hours'], Decimal(2))
            summary = Summary.objects.get(employee_id=employee.pk, period_id=period.pk)
            self.assertEqual((summary.paid_units, summary.overtime_hours, summary.status), (1, 2, 'approved'))
            self.assertEqual(Approval.objects.get(pk=approval.pk).summary_id, summary.pk)
            self.assertEqual(Adjustment.objects.get(audit_id=audit.pk).new_value, '19:00:00')
            migration = import_module('bang_cong.migrations.0008_attendance_summary_and_adjustments')
            migration.backfill_attendance(new_apps, SimpleNamespace(connection=connection))
            self.assertEqual(Summary.objects.count(), 1)
            self.assertEqual(Adjustment.objects.count(), 1)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())

from datetime import date, time
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, Client

from bang_cong.models import KyCong, ChamCong, ChotBangCong, LichLamViec, LichSuTangCa
from bang_cong.services.chot_bang_cong_service import duyet_cong_nhan_vien
from thuong.models import Bonus, payroll_bonus_records
from nhan_vien.models import NhanVien, PhongBan, HocVan, HopDongLaoDong, ChucVu
from nghi_phep.models import LeaveRequest, LeaveDay
from bang_luong.models import PayrollPeriod, Luong, PayrollInput, PayrollAdjustment
from bang_luong.services.tinh_toan import tinh_bang_luong
from bang_luong.services.quy_trinh import duyet_phieu_luong, xu_ly_trang_thai_luong, loi_duyet_luong
from bang_luong.services.quy_trinh import save_input
from bang_luong.services.hien_thi import xuat_du_lieu_luong


class OctoberTrainingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('import_tvt_profiles', password='Training-OnlyForTests@2026', stdout=StringIO())

    def prepare(self, **options):
        call_command('prepare_october_training', stdout=StringIO(), **options)

    def people(self):
        return {e.ma_ho_so:e for e in NhanVien.objects.select_related('nguoi_dung','phong_ban')}

    def test_all_scenarios_have_consistent_sources_without_changing_profiles(self):
        before={model:list(model.objects.order_by('pk').values()) for model in
                [NhanVien,PhongBan,ChucVu,HocVan,HopDongLaoDong,get_user_model()]}
        self.prepare()
        for model, rows in before.items():
            self.assertEqual(list(model.objects.order_by('pk').values()),rows)
        people=self.people()
        self.assertEqual(LichLamViec.objects.count(),31)
        self.assertEqual(LichLamViec.objects.filter(loai_ngay='work').count(),22)
        self.assertFalse(LichLamViec.objects.filter(loai_ngay='holiday').exists())
        self.assertEqual(ChamCong.objects.count(),177)
        self.assertEqual(ChamCong.objects.filter(trang_thai='incomplete').count(),2)
        self.assertEqual(ChamCong.objects.filter(trang_thai='absent').count(),1)
        self.assertEqual(LeaveRequest.objects.count(),5)
        self.assertEqual(LeaveDay.objects.count(),3)
        self.assertEqual(set(Bonus.objects.values_list('status',flat=True)),{'draft','pending','approved','rejected'})
        self.assertEqual(PayrollInput.objects.count(),8)
        self.assertEqual(PayrollInput.objects.filter(verified=False).get().employee.ma_ho_so,'NV08')
        self.assertEqual(PayrollAdjustment.objects.filter(name='Phụ cấp ăn trưa',amount=450000,approved=True).count(),8)
        self.assertEqual(set(ChotBangCong.objects.values_list('nhan_vien__ma_ho_so',flat=True)),{'NV02','NV03','NV06'})
        self.assertEqual(KyCong.objects.get().trang_thai,'pending')
        self.assertEqual(PayrollPeriod.objects.get().status,'pending')
        self.assertEqual(Luong.objects.count(),3)
        self.assertEqual(Luong.objects.get(trang_thai='approved').nhan_vien.ma_ho_so,'NV02')
        self.assertFalse(Luong.objects.filter(trang_thai='paid').exists())
        self.assertFalse(LichSuTangCa.objects.exists())
        self.assertEqual(Luong.objects.get(nhan_vien=people['NV03']).so_gio_tang_ca,Decimal('7.5'))
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV03'],ngay=date(2026,10,24)).tong_cong,0)
        self.assertEqual(ChamCong.objects.get(nhan_vien=people['NV07'],ngay=date(2026,10,9)).tong_cong,1)
        for row in Luong.objects.all():
            amount=sum(payroll_bonus_records(Bonus.objects.filter(employee=row.nhan_vien,year=2026,month=10)).values_list('amount',flat=True),Decimal(0))
            self.assertEqual(row.tong_tien_thuong,amount)

    def test_repeated_command_preserves_user_edits_and_other_months(self):
        other=KyCong.objects.create(nam=2026,thang=9,gio_bat_dau=time(8),bat_dau_nghi_trua=time(12),
            ket_thuc_nghi_trua=time(13),gio_ket_thuc=time(17),gio_chuan=8)
        before=KyCong.objects.values().get(pk=other.pk)
        self.prepare()
        people=self.people()
        record=ChamCong.objects.get(nhan_vien=people['NV01'],ngay=date(2026,10,23))
        record.gio_ra=time(18)
        luu_cham_cong(people['NV05'].nguoi_dung,record,'Người dùng thử chỉnh sửa giờ ra')
        models=[KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,Luong,
                PayrollInput,PayrollAdjustment,LeaveDay,LeaveRequest]
        snapshots={model:list(model.objects.order_by('pk').values()) for model in models}
        self.prepare()
        for model,rows in snapshots.items():
            self.assertEqual(list(model.objects.order_by('pk').values()),rows)
        self.assertEqual(KyCong.objects.values().get(pk=other.pk),before)

    def test_conflicting_existing_data_is_never_overwritten(self):
        day=LichLamViec.objects.create(ngay=date(2026,10,1),loai_ngay='work',cong_chuan=1)
        with self.assertRaises(CommandError): self.prepare()
        self.assertEqual(LichLamViec.objects.count(),1)
        self.assertEqual(LichLamViec.objects.get().pk,day.pk)
        self.assertFalse(ChamCong.objects.exists())
        self.assertFalse(PayrollPeriod.objects.exists())

    def test_dry_run_rolls_back_every_business_record(self):
        self.prepare(dry_run=True)
        for model in [KyCong,ChamCong,LichLamViec,Bonus,PayrollPeriod,Luong,LeaveRequest,LeaveDay]:
            self.assertFalse(model.objects.exists())
        self.assertEqual(NhanVien.objects.count(),8)

    def test_bonus_approval_requires_recalculation_and_never_adds_twice(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        record=Luong.objects.get(nhan_vien=people['NV03'])
        locked=Luong.objects.values().get(nhan_vien=people['NV02'])
        self.assertEqual(record.tong_tien_thuong,0)
        client=Client()
        client.force_login(people['NV08'].nguoi_dung)
        from django.urls import reverse
        url=reverse('thuong:decision',args=[people['NV03'].pk,2026,10])
        response=client.post(url,{'action':'approve'})
        self.assertEqual(response.status_code,302)
        self.assertTrue(loi_duyet_luong(record))
        for attempt in range(2):
            tinh_bang_luong(people['NV05'].nguoi_dung,period.pk,'Tính lại sau duyệt thưởng')
            self.assertEqual(Luong.objects.count(),3)
            current=Luong.objects.get(nhan_vien=people['NV03'])
            self.assertEqual(current.tong_tien_thuong,1050000)
            self.assertEqual(current.so_gio_tang_ca,Decimal('7.5'))
            self.assertEqual(Luong.objects.values().get(nhan_vien=people['NV02']),locked)

    def test_personal_and_department_scopes_are_enforced(self):
        self.prepare()
        people=self.people()
        client=Client(enforce_csrf_checks=True)
        client.force_login(people['NV05'].nguoi_dung)
        client.force_login(people['NV02'].nguoi_dung)
        self.assertEqual(client.get(f'/bang_cong/nhan-vien/{people["NV03"].pk}/?month=10&year=2026').status_code,200)
        self.assertEqual(client.get(f'/bang_cong/nhan-vien/{people["NV04"].pk}/?month=10&year=2026').status_code,404)
        client.force_login(people['NV01'].nguoi_dung)
        self.assertEqual(client.get('/bang_luong/?month=10&year=2026').status_code,302)

    def test_remaining_workflow_can_be_completed_without_payment_in_prepared_state(self):
        self.prepare()
        people=self.people()
        period=PayrollPeriod.objects.get()
        attendance=period.attendance_period
        hr,director=people['NV05'].nguoi_dung,people['NV08'].nguoi_dung
        locked=Luong.objects.filter(trang_thai='approved')
        self.assertEqual(xuat_du_lieu_luong(hr,locked,'csv',10,2026,{}).status_code,200)
        with self.assertRaises(ValidationError): xuat_du_lieu_luong(hr,Luong.objects.all(),'csv',10,2026,{})
        with self.assertRaises(ValidationError): xu_ly_trang_thai_luong(director,period.pk,'paid','Chưa đủ bước','')
        request=LeaveRequest.objects.get(Trang_thai='pending')
        client=Client()
        client.force_login(hr)
        from django.urls import reverse
        self.assertEqual(client.post(reverse('nghi_phep:review',args=[request.pk,'approve'])).status_code,302)
        request.refresh_from_db()
        self.assertEqual(request.Trang_thai,'approved')
        record=ChamCong.objects.get(nhan_vien=people['NV04'],ngay=date(2026,10,30))
        record.trang_thai='leave'
        luu_cham_cong(hr,record,'Cập nhật công sau khi phép đã duyệt')
        record=ChamCong.objects.get(nhan_vien=people['NV05'],ngay=date(2026,10,21))
        record.trang_thai='present';record.gio_ra=time(17)
        luu_cham_cong(hr,record,'Đối chiếu và bổ sung giờ ra')
        inputs=PayrollInput.objects.get(employee=people['NV08'])
        inputs.verified=True
        save_input(hr,inputs)
        for code in ['NV01','NV04','NV05','NV07','NV08']:
            duyet_cong_nhan_vien(hr,people[code],attendance.pk)
        attendance.refresh_from_db()
        self.assertEqual(attendance.trang_thai,'approved')
        tinh_bang_luong(hr,period.pk,'Tính lương sau khi xử lý đủ dữ liệu')
        self.assertEqual(Luong.objects.count(),8)
        xu_ly_trang_thai_luong(director,period.pk,'approve','Đã đối chiếu đủ dữ liệu')
        # Only the isolated test database is paid; the prepared live dataset remains unpaid.
        xu_ly_trang_thai_luong(director,period.pk,'paid','Thử đủ quy trình trong database thử nghiệm','TEST-2026-10')
        self.assertEqual(Luong.objects.filter(trang_thai='paid').count(),8)

    def test_amount_tampering_still_blocks_approval_despite_sqlite_normalization(self):
        self.prepare()
        record=Luong.objects.get(nhan_vien__ma_ho_so='NV06')
        self.assertEqual(loi_duyet_luong(record),'')
        record.luong_theo_cong+=Decimal(1)
        record.save(update_fields=['luong_theo_cong'])
        self.assertTrue(loi_duyet_luong(record))
        with self.assertRaises(ValidationError):
            duyet_phieu_luong(self.people()['NV08'].nguoi_dung,record.pk)