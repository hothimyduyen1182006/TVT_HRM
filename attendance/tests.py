from datetime import date, time
from decimal import Decimal
from io import StringIO
from django.contrib.auth.models import User, Group
from django.core.management import call_command
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, transaction
from django.test import TestCase, Client
from django.utils import timezone
from employees.models import Employee, Department
from leaves.models import LeaveDay
from .models import AttendanceRecord, AttendancePeriod, WorkCalendarDay, AttendanceAuditLog, OvertimeApproval
from .services.workflow import save_record, change_period
from .services.workflow import approve_overtime, submit_overtime, reject_overtime
from django.core.management.base import CommandError


class NonProductionOvertimePolicyTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.other_user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.other
        self.dep.save()
        self.row = save_record(self.hr, AttendanceTests.record(self, check_out=time(19)), 'Giờ ra thực tế')
        self.history = OvertimeApproval.objects.bulk_create([OvertimeApproval(employee=self.emp,
            date=self.row.date, hours=2, multiplier=Decimal('1.5'), approved=True,
            approved_by=self.director, approved_at=timezone.now())])[0]

    def test_all_old_urls_and_services_are_blocked_for_every_role(self):
        admin = User.objects.create_superuser('no-ot-admin', password='TestOnly')
        before = list(OvertimeApproval.objects.values())
        for actor in [self.user, self.other_user, self.hr, self.director, admin]:
            with self.subTest(actor=actor.username):
                client = Client(enforce_csrf_checks=True)
                client.force_login(actor)
                client.get(f'/attendance/{self.row.pk}/')
                for action in ['submit', 'approve', 'reject']:
                    url = f'/attendance/{self.row.pk}/overtime/{action}/'
                    self.assertEqual(client.get(url).status_code, 405)
                    expected=404 if action=='submit' and actor.pk!=self.user.pk else 403
                    self.assertEqual(client.post(url, {'hours': '2', 'multiplier': '1.5',
                        'reason': 'Kiểm thử', 'csrfmiddlewaretoken': client.cookies['csrftoken'].value}).status_code, expected)
                for service,args in [(submit_overtime,(actor,self.row.pk,time(17),time(19),'Kiểm thử')),
                                     (approve_overtime,(actor,self.history.pk,Decimal(2))),
                                     (reject_overtime,(actor,self.history.pk,'Kiểm thử'))]:
                    with self.assertRaises(PermissionDenied):
                        service(*args)
        self.assertEqual(list(OvertimeApproval.objects.values()), before)
        self.assertFalse(AttendanceAuditLog.objects.filter(action__in=['submit_ot','approve_ot','reject_ot']).exists())

    def test_no_ot_ui_for_employee_manager_hr_or_director(self):
        for actor in [self.user, self.other_user, self.hr, self.director]:
            self.client.force_login(actor)
            for url in [f'/attendance/{self.row.pk}/', '/attendance/?month=1&year=2026',
                        f'/attendance/employee/{self.emp.pk}/?month=1&year=2026']:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                for text in ['Gửi yêu cầu duyệt OT', 'Duyệt OT', 'OT đã duyệt', 'Giờ tăng ca', 'Tăng ca (giờ)']:
                    self.assertNotContains(response, text)

    def test_late_checkout_keeps_actual_time_but_caps_paid_work(self):
        self.row.refresh_from_db()
        self.assertEqual(self.row.check_out, time(19))
        self.assertEqual(self.row.work_hours, 8)
        self.assertEqual(self.row.paid_units, 1)
        self.assertEqual(OvertimeApproval.objects.count(), 1)
        self.row.check_out = time(16)
        before = list(OvertimeApproval.objects.values())
        save_record(self.hr, self.row, 'Đối chiếu giờ ra')
        self.row.refresh_from_db()
        self.assertEqual(self.row.work_hours, 7)
        self.assertEqual(self.row.paid_units, Decimal('.875'))
        self.assertEqual(list(OvertimeApproval.objects.values()), before)

    def test_model_writes_and_deletes_are_blocked_and_admin_is_read_only(self):
        with self.assertRaises(PermissionDenied):
            OvertimeApproval(employee=self.emp,date=date(2026,1,6),hours=2,multiplier=1).save()
        with self.assertRaises(PermissionDenied):
            self.history.save()
        with self.assertRaises(PermissionDenied):
            self.history.delete()
        self.hr.is_superuser = self.hr.is_staff = True
        self.hr.save()
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/admin/attendance/overtimeapproval/').status_code, 200)
        self.assertEqual(self.client.post(f'/admin/attendance/overtimeapproval/{self.history.pk}/change/',
            {'approved': 'on'}).status_code, 403)
        self.assertEqual(OvertimeApproval.objects.count(), 1)

    def test_removed_ot_command_is_unavailable(self):
        before = list(OvertimeApproval.objects.values())
        with self.assertRaisesMessage(CommandError, 'Unknown command'):
            call_command('reconcile_overtime', apply=True, actor=self.director.username, stdout=StringIO())
        self.assertEqual(list(OvertimeApproval.objects.values()), before)

    def test_attendance_exports_and_summary_do_not_include_historical_ot(self):
        self.client.force_login(self.hr)
        response = self.client.get(f'/attendance/employee/{self.emp.pk}/export/?month=1&year=2026')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('OT duyệt', response.content.decode('utf-8'))
        self.assertIn('19:00', response.content.decode('utf-8'))
        response = self.client.get(f'/attendance/employee/{self.emp.pk}/?month=1&year=2026')
        self.assertEqual(response.context['summary']['ot'], 0)
        self.assertTrue(all(row['ot'] == 0 for row in response.context['rows']))

    def test_legacy_ot_does_not_block_month_approval(self):
        for employee in [self.emp,self.other]:
            for day in WorkCalendarDay.objects.filter(kind='work'):
                if not AttendanceRecord.objects.filter(employee=employee,date=day.date).exists():
                    save_record(self.hr,AttendanceTests.record(self,employee=employee,date=day.date),'Công trong ca')
        before = list(OvertimeApproval.objects.values())
        change_period(self.director,self.period.pk,'approve','Duyệt công theo ca, không OT')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status,'approved')
        self.assertEqual(list(OvertimeApproval.objects.values()),before)


class ProductionOvertimeTests(TestCase):
    def setUp(self):
        AttendanceTests.setUp(self)
        self.dep.allows_overtime=True
        self.dep.manager=self.other
        self.dep.save()
        self.manager=self.other_user
        self.manager.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.row=save_record(self.hr,AttendanceTests.record(self,check_out=time(19)),'Giờ ra thực tế')
        self.url=f'/attendance/{self.row.pk}/overtime/submit/'
        self.detail=f'/attendance/{self.row.pk}/'
        self.data={'start_time':'17:00','end_time':'19:00','reason':'Hoàn thành đơn hàng','confirm':'on'}

    def send(self,start=time(17),end=time(19)):
        return submit_overtime(self.user,self.row.pk,start,end,'Hoàn thành đơn hàng')

    def test_explicit_submission_requires_confirmation_and_csrf(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertContains(client.get(self.detail),'Gửi yêu cầu duyệt OT')
        self.assertFalse(OvertimeApproval.objects.exists())
        self.assertEqual(client.get(self.url).status_code,405)
        self.assertEqual(client.post(self.url,self.data).status_code,403)
        data={**self.data,'csrfmiddlewaretoken':client.cookies['csrftoken'].value}
        client.post(self.url,{**data,'confirm':''})
        self.assertFalse(OvertimeApproval.objects.exists())
        self.assertEqual(client.post(self.url,data).status_code,302)
        row=OvertimeApproval.objects.get()
        self.assertEqual(row.status,'pending')
        self.assertFalse(row.approved)
        self.assertEqual(row.requested_by,self.user)
        self.assertEqual(row.department,self.dep)
        self.assertEqual(row.requested_hours,2)
        self.assertIsNone(row.approved_at)
        self.assertEqual(AttendanceAuditLog.objects.filter(action='submit_ot').count(),1)

    def test_department_policy_uses_database_and_updates_after_transfer(self):
        self.user.username='unrelated-account-name'
        self.user.save()
        self.dep.name='Đơn vị sản xuất đổi tên'
        self.dep.save()
        self.send()
        self.emp.department=self.other_dep
        self.emp.save()
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(self.detail),'Gửi yêu cầu duyệt OT')
        self.assertEqual(self.client.post(self.url,self.data).status_code,403)
        with self.assertRaises(PermissionDenied):
            approve_overtime(self.manager,OvertimeApproval.objects.get().pk,Decimal(2))

    def test_manager_approves_own_department_only_and_not_self(self):
        row=self.send()
        for actor in [self.user,self.hr,self.director]:
            with self.assertRaises(PermissionDenied):
                approve_overtime(actor,row.pk,Decimal(2))
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager=self.emp
        self.dep.save()
        with self.assertRaises(PermissionDenied):
            approve_overtime(self.user,row.pk,Decimal(2))
        self.dep.manager=self.other
        self.dep.save()
        approve_overtime(self.manager,row.pk,Decimal('1.5'))
        row.refresh_from_db()
        self.assertEqual(row.status,'approved')
        self.assertEqual(row.hours,Decimal('1.5'))
        self.assertEqual(row.approved_by,self.manager)
        self.assertIsNotNone(row.reviewed_at)
        with self.assertRaises(ValidationError):
            approve_overtime(self.manager,row.pk,Decimal(2))
        self.assertEqual(AttendanceAuditLog.objects.filter(action='approve_ot').count(),1)

    def test_approval_and_rejection_post_csrf_and_backend_permissions(self):
        row=self.send()
        url=f'/attendance/overtime/{row.pk}/approve/'
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.manager)
        client.get(self.detail)
        self.assertEqual(client.get(url).status_code,405)
        self.assertEqual(client.post(url,{'hours':'2'}).status_code,403)
        self.assertEqual(client.post(url,{'hours':'2','csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,302)
        row.refresh_from_db()
        self.assertTrue(row.approved)
        self.client.force_login(self.hr)
        self.assertEqual(self.client.post(url,{'hours':'2'}).status_code,403)
        self.assertEqual(self.client.post(f'/attendance/{self.row.pk}/overtime/approve/',{'hours':'2'}).status_code,403)

    def test_cannot_submit_for_someone_else_even_hr_or_superuser(self):
        admin=User.objects.create_superuser('ot-superuser',password='OnlyForTests')
        for actor in [self.manager,self.hr,self.director,admin]:
            self.client.force_login(actor)
            self.assertEqual(self.client.post(self.url,self.data).status_code,404)
            with self.assertRaises(PermissionDenied):
                submit_overtime(actor,self.row.pk,time(17),time(19),'Gửi thay')
        self.assertFalse(OvertimeApproval.objects.exists())

    def test_invalid_intervals_normal_shift_night_and_excess_actual_are_rejected(self):
        for start,end in [(time(19),time(18)),(time(23),time(2)),(time(16),time(18)),
                          (time(17),time(20)),(time(5),time(7))]:
            with self.subTest(start=start,end=end),self.assertRaises(ValidationError):
                self.send(start,end)
        AttendanceRecord.objects.filter(pk=self.row.pk).update(check_out=time(23))
        with self.assertRaisesMessage(ValidationError,'ban đêm'):
            self.send(time(21),time(23))
        self.assertFalse(OvertimeApproval.objects.exists())

    def test_normal_checkout_or_missing_checkout_has_no_button_or_request(self):
        self.client.force_login(self.user)
        for end,status in [(time(17),'present'),(None,'incomplete')]:
            AttendanceRecord.objects.filter(pk=self.row.pk).update(check_out=end,status=status)
            self.assertNotContains(self.client.get(self.detail),'Gửi yêu cầu duyệt OT')
            with self.assertRaises(ValidationError):self.send()

    def test_duplicate_and_overlap_rejected_but_adjacent_intervals_allowed(self):
        self.send(time(17),time(18))
        for start,end in [(time(17),time(18)),(time(17,30),time(19))]:
            with self.assertRaises(ValidationError):self.send(start,end)
        self.send(time(18),time(19))
        self.assertEqual(OvertimeApproval.objects.count(),2)

    def test_rejection_requires_reason_and_is_never_paid_or_resubmitted(self):
        row=self.send()
        with self.assertRaises(ValidationError):reject_overtime(self.manager,row.pk,' ')
        reject_overtime(self.manager,row.pk,'Không đủ căn cứ')
        row.refresh_from_db()
        self.assertEqual(row.status,'rejected')
        self.assertFalse(row.approved)
        self.assertEqual(row.rejection_reason,'Không đủ căn cứ')
        self.assertIsNotNone(row.reviewed_at)
        with self.assertRaises(ValidationError):self.send()
        self.assertEqual(AttendanceAuditLog.objects.filter(action='reject_ot').count(),1)

    def test_cannot_approve_more_than_requested_and_cannot_invalidate_approved_attendance(self):
        row=self.send()
        with self.assertRaises(ValidationError):approve_overtime(self.manager,row.pk,Decimal('2.01'))
        approve_overtime(self.manager,row.pk,Decimal(2))
        self.row.check_out=time(17)
        with self.assertRaises(ValidationError):save_record(self.hr,self.row,'Sửa giờ ra')
        self.row.refresh_from_db()
        self.assertEqual(self.row.check_out,time(19))

    def test_daily_monthly_annual_limits_include_pending_requests(self):
        AttendanceRecord.objects.filter(pk=self.row.pk).update(check_out=time(22))
        with self.assertRaisesMessage(ValidationError,'giới hạn OT ngày'):
            self.send(time(17),time(22))
        history=OvertimeApproval.objects.bulk_create([OvertimeApproval(employee=self.emp,date=date(2026,1,3),
            hours=40,multiplier=2,approved=True)])[0]
        with self.assertRaisesMessage(ValidationError,'40 giờ'):
            self.send()
        OvertimeApproval.objects.filter(pk=history.pk).update(date=date(2026,2,1),hours=199)
        with self.assertRaisesMessage(ValidationError,'200 giờ'):
            self.send()

    def test_day_type_rates_rest_day_lunch_and_holiday(self):
        for day,kind,rate in [(date(2026,1,10),'rest',Decimal(2)),(date(2026,1,6),'holiday',Decimal(3))]:
            WorkCalendarDay.objects.filter(date=day).update(kind=kind,expected_units=0)
            record=save_record(self.hr,AttendanceTests.record(self,date=day,check_out=time(10)),'Làm ngoài ca')
            row=submit_overtime(self.user,record.pk,time(8),time(10),'Đơn hàng')
            self.assertEqual(row.multiplier,rate)
        record=save_record(self.hr,AttendanceTests.record(self,date=date(2026,1,11),check_out=time(14)),'Ngày nghỉ')
        with self.assertRaisesMessage(ValidationError,'nghỉ trưa'):
            submit_overtime(self.user,record.pk,time(8),time(14),'Ngày nghỉ')

    def test_locked_period_and_payroll_block_submission_and_reviews(self):
        from payroll.models import PayrollPeriod
        row=self.send()
        self.period.status='approved';self.period.save()
        with self.assertRaises(ValidationError):approve_overtime(self.manager,row.pk,Decimal(2))
        with self.assertRaises(ValidationError):reject_overtime(self.manager,row.pk,'Lý do')
        self.period.status='pending';self.period.save()
        PayrollPeriod.objects.create(attendance_period=self.period,status='paid')
        with self.assertRaises(ValidationError):approve_overtime(self.manager,row.pk,Decimal(2))
        with self.assertRaises(ValidationError):self.send(time(17),time(18))

    def test_pending_ot_must_be_resolved_before_approving_attendance(self):
        from .services.workflow import approve_employee
        self.send()
        with self.assertRaisesMessage(ValidationError,'OT chờ duyệt'):
            approve_employee(self.hr,self.emp,self.period.pk)
        with self.assertRaisesMessage(ValidationError,'OT chờ duyệt'):
            change_period(self.director,self.period.pk,'approve','Khóa kỳ')

    def test_personal_month_has_link_only_when_eligible_and_hr_sees_approved_total(self):
        self.client.force_login(self.user)
        url='/attendance/personal/?month=1&year=2026'
        self.assertContains(self.client.get(url),'Gửi yêu cầu duyệt OT')
        row=self.send()
        self.assertNotContains(self.client.get(self.detail),'Gửi yêu cầu duyệt OT')
        approve_overtime(self.manager,row.pk,Decimal(2))
        self.client.force_login(self.hr)
        response=self.client.get(f'/attendance/employee/{self.emp.pk}/?month=1&year=2026')
        self.assertEqual(response.context['summary']['ot'],2)
        self.assertContains(response,'OT đã duyệt:')

    def test_cannot_enable_a_second_overtime_department(self):
        self.other_dep.allows_overtime=True
        with self.assertRaises(IntegrityError),transaction.atomic():
            self.other_dep.save()


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
                 lunch_start=time(12), lunch_end=time(13), end_time=time(17), standard_hours=8,
                 policy_confirmed=True)
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

    def test_after_hours_is_not_automatic_ot(self):
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
                    response = self.client.get(f'/attendance/{row.pk}/')
                    self.assertEqual(response.status_code, 200)
                    self.assertFalse(response.context['can_edit'])
                    self.assertNotContains(response, f'href="/attendance/{row.pk}/edit/"')
                    self.assertEqual(self.client.get(f'/attendance/{row.pk}/edit/').status_code, 403)
                    audits = AttendanceAuditLog.objects.count()
                    response = self.client.post(f'/attendance/{row.pk}/edit/', {
                        'employee': self.emp.pk, 'date': '2026-01-05', 'check_in': '09:00',
                        'check_out': '17:00', 'status': 'present', 'note': 'Thay đổi', 'reason': 'Sửa'})
                    self.assertEqual(response.status_code, 403)
                    row.refresh_from_db()
                    self.assertEqual(row.check_in, time(8))
                    self.assertEqual(row.note, '')
                    self.assertEqual(AttendanceAuditLog.objects.count(), audits)
                    response = self.client.post('/attendance/new/', {
                        'employee': self.emp.pk, 'date': '2026-01-06', 'check_in': '08:00',
                        'check_out': '17:00', 'status': 'present', 'reason': 'Tạo thêm'})
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, 'Kỳ công đã duyệt, cần mở lại trước.')
                    self.assertFalse(AttendanceRecord.objects.filter(employee=self.emp,
                                                                    date=date(2026, 1, 6)).exists())

    def test_pending_attendance_keeps_edit_link_and_allows_update(self):
        row = save_record(self.hr, self.record(), 'Tạo công')
        self.client.force_login(self.hr)
        response = self.client.get(f'/attendance/{row.pk}/')
        self.assertTrue(response.context['can_edit'])
        self.assertContains(response, f'href="/attendance/{row.pk}/edit/"')
        self.assertEqual(self.client.get(f'/attendance/{row.pk}/edit/').status_code, 200)
        response = self.client.post(f'/attendance/{row.pk}/edit/', {
            'employee': self.emp.pk, 'date': '2026-01-05', 'check_in': '09:00',
            'check_out': '17:00', 'status': 'present', 'note': 'Đi muộn', 'reason': 'Điều chỉnh'})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.check_in, time(9))

    def test_self_and_department_scopes(self):
        own = save_record(self.hr, self.record(), 'Công')
        other = save_record(self.hr, self.record(employee=self.other), 'Công')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(f'/attendance/{own.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/attendance/{other.pk}/').status_code, 404)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/attendance/{other.pk}/').status_code, 404)

    def test_lists_and_create(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get('/attendance/?month=1&year=2026').status_code, 200)
        response = self.client.get('/attendance/?month=13&year=2026')
        self.assertTrue(response.context['form'].errors)
        response = self.client.post('/attendance/new/', {'employee': self.emp.pk, 'date': '2026-01-05',
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
        self.assertRedirects(self.client.get('/dashboard/'), '/attendance/', fetch_redirect_response=False)
        response = self.client.get('/employees/')
        self.assertEqual(response.status_code, 403)
        response = self.client.get('/employees/me/')
        self.assertContains(response, 'NV01')
        self.assertNotContains(response, 'NV02')

    def test_monthly_summary_groups_employee_and_filters(self):
        save_record(self.hr, self.record(), 'Ngày 1')
        save_record(self.hr, self.record(date=date(2026, 1, 6), check_in=time(9)), 'Ngày 2')
        save_record(self.hr, self.record(employee=self.other), 'Phòng khác')
        self.client.force_login(self.hr)
        response = self.client.get('/attendance/', {'month': 1, 'year': 2026, 'q': 'NV01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['rows']), 1)
        row = response.context['rows'][0]
        self.assertEqual(row['paid'], Decimal('1.875'))
        self.assertEqual(row['late_count'], 1)
        self.assertEqual(row['late'], 60)
        self.assertContains(response, 'BẢNG CÔNG TỔNG HỢP')
        response = self.client.get('/attendance/', {'month': 1, 'year': 2026, 'department': self.dep.pk})
        self.assertEqual(len(response.context['rows']), 1)

    def test_personal_month_and_missing_days(self):
        save_record(self.hr, self.record(), 'Ngày đủ giờ')
        self.client.force_login(self.user)
        response = self.client.get('/attendance/', {'month': 1, 'year': 2026})
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
        url = f'/attendance/employee/{self.emp.pk}/'
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
        url = f'/attendance/employee/{self.emp.pk}/history/'
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
        response = self.client.get(f'/attendance/employee/{self.emp.pk}/history/?month=1&year=2026')
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
            self.assertEqual(self.client.get(f'/attendance/employee/{self.other.pk}/{suffix}').status_code, 404)
        self.assertEqual(self.client.get(f'/attendance/employee/{self.emp.pk}/export/').status_code, 403)
        self.user.groups.add(Group.objects.get_or_create(name='Trưởng phòng')[0])
        self.dep.manager = self.emp
        self.dep.save()
        self.assertEqual(self.client.get(f'/attendance/employee/{self.other.pk}/history/').status_code, 404)

    def test_attendance_csv_exports_filter_and_escape(self):
        row = save_record(self.hr, self.record(), 'Tạo')
        row.note = '=HYPERLINK("example")'
        save_record(self.hr, row, 'Nhân sự sửa ghi chú')
        self.client.force_login(self.hr)
        url = f'/attendance/employee/{self.emp.pk}/export/'
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
        pages = [('/', None), ('/dashboard/', 'DASHBOARD'), ('/employees/', 'NHÂN VIÊN'),
                 ('/attendance/', 'BẢNG CÔNG'), ('/payroll/', 'BẢNG LƯƠNG'),
                 ('/payroll/inputs/', 'BẢNG LƯƠNG'), ('/admin/bonuses/bonus/', 'BẢNG THƯỞNG'),
                 ('/admin/leaves/leaveday/', 'NGHỈ PHÉP'), ('/admin/', None)]
        for url, active in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
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
        response = self.client.get('/attendance/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        response = self.client.get(f'/attendance/employee/{self.emp.pk}/?month=1&year=2026')
        url = f'/attendance/employee/{self.emp.pk}/approve/{self.period.pk}/'
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
        url = f'/attendance/employee/{self.emp.pk}/approve/{self.period.pk}/'
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
        response = self.client.get('/attendance/?month=1&year=2026')
        states = {r['employee'].pk: r['state'] for r in response.context['rows']}
        self.assertEqual(states[self.emp.pk], 'approved')
        self.assertEqual(states[self.other.pk], 'empty')
        row = AttendanceRecord.objects.filter(employee=self.emp).first()
        with self.assertRaises(ValidationError):
            save_record(self.hr, row, 'Không sửa công đã duyệt riêng')
        for day in WorkCalendarDay.objects.filter(kind='work'):
            save_record(self.hr, self.record(employee=self.other, date=day.date), 'Đối chiếu')
        self.client.post(f'/attendance/employee/{self.other.pk}/approve/{self.period.pk}/')
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, 'approved')
        self.assertEqual(set(self.period.employee_ids), {self.emp.pk, self.other.pk})

    def test_approved_payroll_blocks_reopen_button_and_service(self):
        from payroll.models import PayrollPeriod
        self.period.status = 'approved'
        self.period.save()
        PayrollPeriod.objects.create(attendance_period=self.period, status='approved')
        self.client.force_login(self.director)
        response = self.client.get('/attendance/?month=1&year=2026')
        self.assertNotContains(response, 'attendance-approval-title')
        self.assertNotContains(response, 'name="action" value="reopen"')
        with self.assertRaises(ValidationError):
            change_period(self.director, self.period.pk, 'reopen', 'Không vượt khóa lương')
