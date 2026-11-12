from datetime import date, time
from decimal import Decimal
from io import StringIO
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.utils import timezone
from nhan_vien.models import Employee, Department
from nghi_phep.models import LeaveDay
from .models import AttendanceRecord, AttendancePeriod, WorkCalendarDay, AttendanceAuditLog, OvertimeApproval
from .services.workflow import save_record, change_period
from django.core.management.base import CommandError


class AutomaticOvertimeTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.period.month=10
        self.period.save()
        for day in range(1,32):
            value=date(2026,10,day)
            work=value.weekday()<5
            WorkCalendarDay.objects.create(date=value,kind='work' if work else 'rest',expected_units=1 if work else 0)

    def record(self,**values):
        return AttendanceTests.record(self,date=date(2026,10,5),**values)

    def test_checkout_boundaries_for_all_departments(self):
        for employee in [self.emp,self.other]:
            for end,expected in [(time(16,30),0),(time(17),0),(time(17,30),Decimal('.5')),
                                 (time(18),1),(time(19),2),(time(20),3)]:
                with self.subTest(employee=employee.code,end=end):
                    row=AttendanceRecord.objects.filter(employee=employee,date=date(2026,10,5)).first() or self.record(employee=employee)
                    row.check_out=end
                    save_record(self.hr,row,'Kiểm thử tháng 10')
                    row.refresh_from_db()
                    self.assertEqual(row.overtime_hours,expected)
                    self.assertEqual(row.check_out,end)
                    self.assertLessEqual(row.work_hours,8)
                    self.assertLessEqual(row.paid_units,1)
        self.assertFalse(OvertimeApproval.objects.exists())

    def test_missing_checkout_invalid_status_and_late_arrival(self):
        row=self.record(check_out=None,status='incomplete')
        row.save()
        self.assertEqual(row.overtime_hours,0)
        row.status='absent'
        row.check_in=None
        row.check_out=time(20)
        self.assertEqual(row.overtime_hours,0)
        self.assertEqual(self.record(check_in=time(18),check_out=time(19)).overtime_hours,1)

    def test_hr_edit_changes_ot_and_audit_without_changing_history(self):
        row=save_record(self.hr,self.record(check_out=time(19)),'Tạo công')
        history=OvertimeApproval.objects.bulk_create([OvertimeApproval(employee=self.emp,date=row.date,hours=9,multiplier=3,status='pending')])[0]
        before=list(OvertimeApproval.objects.values())
        row.check_out=time(18)
        save_record(self.hr,row,'Sửa giờ ra')
        self.assertEqual(row.overtime_hours,1)
        self.assertEqual(row.work_hours,8)
        log=AttendanceAuditLog.objects.filter(action='edit_record').latest('pk')
        self.assertEqual(Decimal(log.before['overtime_hours']),2)
        self.assertEqual(Decimal(log.after['overtime_hours']),1)
        self.assertEqual(list(OvertimeApproval.objects.values()),before)
        for operation in [history.save,history.delete]:
            with self.assertRaises(PermissionDenied): operation()

    def test_old_urls_are_missing_for_every_role_and_method(self):
        row=save_record(self.hr,self.record(check_out=time(19)),'Công thực tế')
        self.other_user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        before=list(AttendanceRecord.objects.values())
        for actor in [self.user,self.other_user,self.hr,self.director]:
            client=Client(enforce_csrf_checks=True)
            client.force_login(actor)
            for action in ['submit','approve','reject']:
                for url in [f'/bang_cong/{row.pk}/overtime/{action}/',f'/bang_cong/overtime/{row.pk}/{action}/']:
                    self.assertEqual(client.get(url).status_code,404)
                    self.assertEqual(client.post(url,{'hours':'99'}).status_code,404)
        self.assertEqual(list(AttendanceRecord.objects.values()),before)


    def test_ui_exports_and_personal_scope_share_hours(self):
        row=save_record(self.hr,self.record(check_out=time(19)),'Công thực tế')
        for actor in [self.user,self.hr,self.director]:
            self.client.force_login(actor)
            response=self.client.get(f'/bang_cong/{row.pk}/')
            self.assertContains(response,'Tăng ca tự động')
            for label in ['Gửi yêu cầu duyệt OT','Duyệt OT','Từ chối OT']:
                self.assertNotContains(response,label)
        self.client.force_login(self.user)
        response=self.client.get('/bang_cong/personal/?month=10&year=2026')
        self.assertEqual(response.context['summary']['ot'],2)
        self.assertNotContains(response,'OT tự động:')
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.get(f'/bang_cong/{row.pk}/').status_code,404)
        self.client.force_login(self.hr)
        response=self.client.get(f'/bang_cong/employee/{self.emp.pk}/export/?month=10&year=2026')
        self.assertIn('OT tự động (giờ)',response.content.decode('utf-8-sig'))

    def test_rest_holiday_and_night_are_handled_separately(self):
        from .services.calculations import automatic_overtime,payroll_overtime
        day=WorkCalendarDay.objects.get(date=date(2026,10,5))
        row=self.record()
        for kind,rate in [('rest',2),('holiday',3)]:
            day.kind,day.expected_units=kind,0
            day.save()
            row=save_record(self.hr,row,'Ngày đặc biệt')
            item=automatic_overtime(row,self.period,day)
            self.assertEqual(item['hours'],8)
            self.assertEqual(item['multiplier'],rate)
            self.assertEqual(row.paid_units,0)
        row.check_out=time(23)
        save_record(self.hr,row,'Giữ giờ ra ban đêm')
        self.assertEqual(row.check_out,time(23))
        with self.assertRaisesMessage(ValidationError,'ban đêm'): payroll_overtime(self.emp,2026,10)
        row.check_out=time(2)
        with self.assertRaises(ValidationError): save_record(self.hr,row,'Ca qua đêm chưa hỗ trợ')

    def test_locked_period_still_blocks_changes(self):
        row=save_record(self.hr,self.record(check_out=time(19)),'Công thực tế')
        self.period.status='approved'
        self.period.save()
        row.check_out=time(20)
        with self.assertRaises(ValidationError): save_record(self.hr,row,'Không vượt khóa')
        row.refresh_from_db()
        self.assertEqual(row.check_out,time(19))

    def test_checkout_punch_immediately_exposes_ot_without_creating_request(self):
        from datetime import datetime
        from unittest.mock import patch
        from .services.clocking import punch
        with patch('bang_cong.services.clocking.timezone.localtime',return_value=datetime(2026,10,5,8)):
            punch(self.user,'in')
        with patch('bang_cong.services.clocking.timezone.localtime',return_value=datetime(2026,10,5,18,30)):
            row=punch(self.user,'out')
        row.refresh_from_db()
        self.assertEqual(row.overtime_hours,Decimal('1.5'))
        self.assertEqual(row.check_out,time(18,30))
        self.assertEqual(row.paid_units,1)
        self.assertFalse(OvertimeApproval.objects.exists())

    def test_pending_historical_requests_no_longer_block_attendance_approval(self):
        from .services.workflow import approve_employee
        for day in WorkCalendarDay.objects.filter(date__month=10,kind='work'):
            save_record(self.hr,AttendanceTests.record(self,date=day.date),'Công tháng 10')
        OvertimeApproval.objects.bulk_create([OvertimeApproval(employee=self.emp,date=date(2026,10,5),
            hours=2,multiplier=Decimal('1.5'),status='pending')])
        before=list(OvertimeApproval.objects.values())
        approve_employee(self.hr,self.emp,self.period.pk)
        self.assertTrue(self.period.employee_approvals.filter(employee=self.emp).exists())
        self.assertEqual(list(OvertimeApproval.objects.values()),before)


class AttendanceTests(TestCase):
    def setUp(self):
        self.hr = User.objects.create_user('hr')
        self.hr.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        self.director = User.objects.create_user('director')
        self.director.groups.add(Group.objects.get_or_create(name='Giám đốc')[0])
        self.user = User.objects.create_user('employee')
        self.other_user = User.objects.create_user('other')
        self.dep = Department.objects.create(code='A', name='Phòng A')
        self.other_dep = Department.objects.create(code='B', name='Phòng B')
        self.emp = Employee.objects.create(code='NV01', full_name='Nhân viên 1', user=self.user,
                    department=self.dep, hire_date=date(2020, 1, 1), base_salary=Decimal('22000000'))
        self.other = Employee.objects.create(code='NV02', full_name='Nhân viên 2', user=self.other_user,
                    department=self.other_dep, hire_date=date(2020, 1, 1), base_salary=Decimal('22000000'))
        self.period = AttendancePeriod.objects.create(month=1, year=2026, start_time=time(8),
                 lunch_start=time(12), lunch_end=time(13), end_time=time(17), standard_hours=8)
        for day in range(1, 32):
            value = date(2026, 1, day)
            work = value.weekday() < 5
            WorkCalendarDay.objects.create(date=value, kind='work' if work else 'rest', expected_units=1 if work else 0)

    def record(self, employee=None, **kwargs):
        values = dict(employee=employee or self.emp, date=date(2026, 1, 5),
                      check_in=time(8), check_out=time(17), status='present')
        values.update(kwargs)
        return AttendanceRecord(**values)

    def test_lunch_and_regular_hours(self):
        row = save_record(self.hr, self.record(), 'Kiểm tra')
        self.assertEqual(row.work_hours, 8)
        self.assertEqual(row.paid_units, 1)
        self.assertEqual(AttendanceAuditLog.objects.count(), 1)

    def test_late_and_half_day(self):
        row = save_record(self.hr, self.record(check_in=time(9)), 'Đi muộn')
        self.assertEqual(row.late_minutes, 60)
        self.assertEqual(row.paid_units, Decimal('.875'))
        row.check_in, row.check_out = time(8), time(12)
        save_record(self.hr, row, 'Nửa ngày')
        self.assertEqual(row.actual_units, Decimal('.5'))

    def test_after_hours_does_not_double_normal_work(self):
        row = save_record(self.hr, self.record(check_out=time(20)), 'Kiểm tra')
        self.assertEqual(row.work_hours, 8)
        self.assertEqual(row.actual_units, 1)

    def test_invalid_checkout(self):
        for out in [time(7), time(8)]:
            with self.assertRaises(ValidationError):
                save_record(self.hr, self.record(check_out=out), 'Sai giờ')

    def test_duplicate_database_constraint(self):
        save_record(self.hr, self.record(), 'Lần 1')
        with self.assertRaises(IntegrityError), transaction.atomic():
            AttendanceRecord.objects.create(employee=self.emp, date=date(2026, 1, 5), status='absent')

    def test_paid_and_unpaid_leave(self):
        leave = LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 5), units=1, paid=True,
                                        reason='Phép', approved=True)
        row = save_record(self.hr, self.record(check_in=None, check_out=None, status='leave'), 'Phép')
        self.assertEqual(row.paid_units, 1)
        self.assertEqual(row.actual_units, 0)
        leave.paid = False
        leave.save()
        save_record(self.hr, row, 'Không lương')
        self.assertEqual(row.paid_units, 0)

    def test_overlap_rejected(self):
        LeaveDay.objects.create(employee=self.emp, date=date(2026, 1, 5), units=1, paid=True,
                                reason='Phép', approved=True)
        with self.assertRaises(ValidationError):
            save_record(self.hr, self.record(), 'Trùng')

    def test_ordinary_user_cannot_edit(self):
        with self.assertRaises(PermissionDenied):
            save_record(self.user, self.record(), 'Không có quyền')

    def test_locked_period(self):
        self.period.status = 'approved'
        self.period.save()
        with self.assertRaises(ValidationError):
            save_record(self.hr, self.record(), 'Kỳ khóa')

    def test_approval_requires_complete_data(self):
        with self.assertRaises(ValidationError):
            change_period(self.director, self.period.pk, 'approve', 'Thiếu công')

    def test_approved_attendance_blocks_edit_page_and_post(self):
        from .models import EmployeeAttendanceApproval
        row = save_record(self.hr, self.record(), 'Tạo công')
        for lock in ['period', 'employee']:
            if lock == 'period':
                self.period.status = 'approved'
                self.period.save()
            else:
                self.period.status = 'pending'
                self.period.save()
                EmployeeAttendanceApproval.objects.create(period=self.period, employee=self.emp,
                                                          approved_by=self.director)
            for actor in [self.hr, self.director]:
                with self.subTest(lock=lock, actor=actor.username):
                    self.client.force_login(actor)
                    response = self.client.get(f'/bang_cong/{row.pk}/')
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.context['can_edit'])
                    self.assertNotContains(response, f'href="/bang_cong/{row.pk}/edit/"')
                    self.assertEqual(self.client.get(f'/bang_cong/{row.pk}/edit/').status_code, 403)
                    audits = AttendanceAuditLog.objects.count()
                    response = self.client.post(f'/bang_cong/{row.pk}/edit/', {
                        'employee': self.emp.pk, 'date': '2026-01-05', 'check_in': '09:00',
                        'check_out': '17:00', 'status': 'present', 'note': 'Thay đổi', 'reason': 'Sửa'})
                    self.assertEqual(response.status_code, 403)
                    row.refresh_from_db()
                    self.assertEqual(row.check_in, time(8))
                    self.assertEqual(row.note, '')
                    self.assertEqual(AttendanceAuditLog.objects.count(), audits)
                    new_day = 6 if actor == self.hr else 7
                    response = self.client.post('/bang_cong/new/', {
                        'employee': self.emp.pk, 'date': f'2026-01-{new_day:02}', 'check_in': '08:00',
                        'check_out': '17:00', 'status': 'present', 'reason': 'Tạo thêm'})
                    if lock == 'period':
                        self.assertEqual(response.status_code, 200)
                        self.assertContains(response, 'Kỳ công đã duyệt, cần mở lại trước.')
                        self.assertFalse(AttendanceRecord.objects.filter(employee=self.emp,
                                                                        date=date(2026, 1, new_day)).exists())
                    else:
                        # Quy tắc của bản 616e798: chỉ khóa bản ghi đã có khi duyệt nhân viên.
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(AttendanceRecord.objects.filter(employee=self.emp,
                                                                       date=date(2026, 1, new_day)).exists())

    def test_pending_attendance_keeps_edit_link_and_allows_update(self):
        row = save_record(self.hr, self.record(), 'Tạo công')
        self.client.force_login(self.hr)
        response = self.client.get(f'/bang_cong/{row.pk}/')
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, f'href="/bang_cong/{row.pk}/edit/"')
        self.assertEqual(self.client.get(f'/bang_cong/{row.pk}/edit/').status_code, 200)
        response = self.client.post(f'/bang_cong/{row.pk}/edit/', {
            'employee': self.emp.pk, 'date': '2026-01-05', 'check_in': '09:00',
            'check_out': '17:00', 'status': 'present', 'note': 'Đi muộn', 'reason': 'Điều chỉnh'})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.check_in, time(9))

    def test_self_and_department_scopes(self):
        own = save_record(self.hr, self.record(), 'Công')
        other = save_record(self.hr, self.record(employee=self.other), 'Công')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/bang_cong/{own.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/bang_cong/{other.pk}/').status_code, 404)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/bang_cong/{other.pk}/').status_code, 404)

    def test_lists_and_create(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/bang_cong/?month=1&year=2026').status_code, 200)
        response = self.client.get('/bang_cong/?month=13&year=2026')
        self.assertTrue(response.context['form'].errors)
        response = self.client.post('/bang_cong/new/', {'employee': self.emp.pk, 'date': '2026-01-05',
            'check_in': '08:00', 'check_out': '17:00', 'status': 'present', 'note': '', 'reason': 'Tạo'})
        self.assertEqual(response.status_code, 302)

    def test_full_month_approval_and_audit(self):
        for employee in [self.emp, self.other]:
            for day in WorkCalendarDay.objects.filter(kind='work'):
                save_record(self.hr, self.record(employee=employee, date=day.date), 'Kiểm tra ngày')
        change_period(self.director, self.period.pk, 'approve', 'Đủ dữ liệu')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertEqual(set(self.period.employee_ids), {self.emp.pk, self.other.pk})
        change_period(self.director, self.period.pk, 'reopen', 'Cần kiểm tra lại')
        self.period.refresh_from_db()
        self.assertEqual(self.period.revision, 2)

    def test_calendar_command_does_not_overwrite(self):
        from django.core.management import call_command, CommandError
        from io import StringIO
        call_command('create_calendar', year=2026, month=2, workdays='0,1,2,3,4', holidays='2026-02-02', stdout=StringIO())
        self.assertEqual(WorkCalendarDay.objects.get(date=date(2026, 2, 2)).kind, 'holiday')
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
        save_record(self.hr, self.record(), 'Ngày 1')
        save_record(self.hr, self.record(date=date(2026, 1, 6), check_in=time(9)), 'Ngày 2')
        save_record(self.hr, self.record(employee=self.other), 'Phòng khác')
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
        save_record(self.hr, self.record(), 'Ngày đủ giờ')
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
        save_record(self.hr, self.record(check_in=time(9)), 'Đi muộn')
        self.client.force_login(self.hr)
        url = f'/bang_cong/employee/{self.emp.pk}/'
        response = self.client.get(url, {'month': 1, 'year': 2026, 'state': 'late'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 1)
        self.assertContains(response, 'Đi làm trễ')
        response = self.client.get(url, {'month': 1, 'year': 2026, 'start': '2026-01-10', 'end': '2026-01-02'})
        self.assertTrue(response.context['form'].errors)
        response = self.client.get(url, {'month': 1, 'year': 2026, 'page': 2})
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_history_field_differences_and_filters(self):
        row = save_record(self.hr, self.record(check_in=time(9)), 'Tạo ban đầu')
        row.check_in = time(8, 30)
        save_record(self.hr, row, 'Đối chiếu máy chấm công')
        self.client.force_login(self.hr)
        url = f'/bang_cong/employee/{self.emp.pk}/history/'
        response = self.client.get(url, {'month': 1, 'year': 2026, 'field': 'check_in'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 1)
        change = response.context['rows'][0]
        self.assertEqual(change['old'], '09:00:00')
        self.assertEqual(change['new'], '08:30:00')
        self.assertContains(response, 'Đối chiếu máy chấm công')
        response = self.client.get(url, {'month': 1, 'year': 2026, 'actor': self.other_user.pk})
        self.assertTrue(response.context['form'].errors)

    def test_history_excludes_creation_noop_and_automatic_events(self):
        from .services.presentation import history_logs, history_rows
        from .services.workflow import record_values
        row = save_record(self.hr, self.record(), 'Tạo mới')
        self.assertEqual(history_rows(history_logs(self.emp, 2026, 1)), [])
        count = AttendanceAuditLog.objects.count()
        save_record(self.hr, row, 'Lưu mà không thay đổi')
        self.assertEqual(AttendanceAuditLog.objects.count(), count)
        before = record_values(row)
        after = {**before, 'work_hours': '7.0000'}
        for action in ['recalculate', 'approve_employee']:
            AttendanceAuditLog.objects.create(actor=self.hr, action=action, reason='Tự động', before=before, after=after)
        AttendanceAuditLog.objects.create(actor=self.hr, action='save_record', reason='Bản ghi tạo mới cũ', before={}, after=before)
        self.assertEqual(history_rows(history_logs(self.emp, 2026, 1)), [])
        self.client.force_login(self.hr)
        response = self.client.get(f'/bang_cong/employee/{self.emp.pk}/history/?month=1&year=2026')
        self.assertContains(response, 'Chưa có điều chỉnh chấm công')

    def test_history_preserves_legacy_manual_edits(self):
        from .services.presentation import history_logs, history_rows
        values = {'employee_id': str(self.emp.pk), 'date': '2026-01-05', 'check_in': '08:00:00'}
        AttendanceAuditLog.objects.create(actor=self.hr, action='save_record', reason='Chỉnh sửa phiên bản cũ',
            before={**values, 'check_in': '09:00:00'}, after=values)
        rows = history_rows(history_logs(self.emp, 2026, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['old'], '09:00:00')
        self.assertEqual(rows[0]['new'], '08:00:00')

    def test_new_pages_enforce_department_scope(self):
        self.client.force_login(self.user)
        for suffix in ['', 'history/']:
            self.assertEqual(self.client.get(f'/bang_cong/employee/{self.other.pk}/{suffix}').status_code, 404)
        self.assertEqual(self.client.get(f'/bang_cong/employee/{self.emp.pk}/export/').status_code, 403)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/bang_cong/employee/{self.other.pk}/history/').status_code, 404)

    def test_attendance_csv_exports_filter_and_escape(self):
        row = save_record(self.hr, self.record(), 'Tạo')
        row.note = '=HYPERLINK("example")'
        save_record(self.hr, row, 'Nhân sự sửa ghi chú')
        self.client.force_login(self.hr)
        url = f'/bang_cong/employee/{self.emp.pk}/export/'
        response = self.client.get(url, {'month': 1, 'year': 2026, 'start': '2026-01-05', 'end': '2026-01-05'})
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=HYPERLINK", response.content.decode('utf-8-sig'))
        response = self.client.get(url, {'month': 1, 'year': 2026, 'mode': 'history', 'field': 'note'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Ghi chú', response.content.decode('utf-8-sig'))
        self.assertEqual(self.client.get(url, {'month': 13, 'year': 2026}).status_code, 400)

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

    def test_employee_approval_button_next_to_history(self):
        self.client.force_login(self.hr)
        response = self.client.get('/bang_cong/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        response = self.client.get(f'/bang_cong/employee/{self.emp.pk}/?month=1&year=2026')
        url = f'/bang_cong/employee/{self.emp.pk}/approve/{self.period.pk}/'
        self.assertContains(response, f'action="{url}"', count=1)
        html = response.content.decode()
        self.assertLess(html.index('Lịch sử điều chỉnh công'), html.index('>Duyệt bảng công</button>'))
        self.assertLess(html.index('</table>'), html.index('class="at-approval-footer"'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_approval_post_validates_data_and_records_actor(self):
        from .models import EmployeeAttendanceApproval
        self.client.force_login(self.hr)
        url = f'/bang_cong/employee/{self.emp.pk}/approve/{self.period.pk}/'
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'còn thiếu ngày')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'pending')
        for day in WorkCalendarDay.objects.filter(kind='work'):
            save_record(self.hr, self.record(date=day.date), 'Đối chiếu')
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'Đã duyệt bảng công của')
        self.assertNotContains(response, f'action="{url}"')
        self.assertContains(response, 'disabled>Đã duyệt</button>')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'pending')
        self.assertEqual(EmployeeAttendanceApproval.objects.get(employee=self.emp).approved_by, self.hr)
        self.assertFalse(EmployeeAttendanceApproval.objects.filter(employee=self.other).exists())
        self.assertTrue(AttendanceAuditLog.objects.filter(actor=self.hr, action='approve_employee').exists())
        response = self.client.get('/bang_cong/?month=1&year=2026')
        states = {r['employee'].pk: r['state'] for r in response.context['rows']}
        self.assertEqual(states[self.emp.pk], 'approved')
        self.assertEqual(states[self.other.pk], 'empty')
        row = AttendanceRecord.objects.filter(employee=self.emp).first()
        with self.assertRaises(ValidationError):
            save_record(self.hr, row, 'Không sửa công đã duyệt riêng')
        for day in WorkCalendarDay.objects.filter(kind='work'):
            save_record(self.hr, self.record(employee=self.other, date=day.date), 'Đối chiếu')
        self.client.post(f'/bang_cong/employee/{self.other.pk}/approve/{self.period.pk}/')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertEqual(set(self.period.employee_ids), {self.emp.pk, self.other.pk})

    def test_approved_payroll_blocks_reopen_button_and_service(self):
        from bang_luong.models import PayrollPeriod
        self.period.status = 'approved'
        self.period.save()
        PayrollPeriod.objects.create(attendance_period=self.period, status='approved')
        self.client.force_login(self.director)
        response = self.client.get('/bang_cong/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        self.assertNotContains(response, 'name="action" value="reopen"')
        with self.assertRaises(ValidationError):
            change_period(self.director, self.period.pk, 'reopen', 'Không vượt khóa lương')
