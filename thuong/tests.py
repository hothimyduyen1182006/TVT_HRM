from datetime import date, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from bang_cong.models import AttendancePeriod, AttendanceRecord, WorkCalendarDay
from nhan_vien.models import Department, Employee
from .models import Bonus


class AutomaticBonusPostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department = Department.objects.create(code='BA', name='Phòng A')
        other_department = Department.objects.create(code='BB', name='Phòng B')
        cls.people = {}
        for name, room, role in [
            ('employee', department, 'Nhân viên'),
            ('manager', department, 'Trưởng phòng'),
            ('outsider', other_department, 'Nhân viên'),
        ]:
            user = get_user_model().objects.create_user(name)
            user.groups.add(Group.objects.get_or_create(name=role)[0])
            cls.people[name] = Employee.objects.create(user=user, code=name,
                full_name=name, department=room, hire_date=date(2020, 1, 1), base_salary=10000000)
        department.manager = cls.people['manager']
        department.save(update_fields=['manager'])
        cls.hr = get_user_model().objects.create_user('hr')
        cls.hr.groups.add(Group.objects.get_or_create(name='Nhân sự')[0])
        cls.director = get_user_model().objects.create_user('director')
        cls.director.groups.add(Group.objects.get_or_create(name='Giám đốc')[0])
        AttendancePeriod.objects.create(month=1, year=2026, start_time=time(8),
            lunch_start=time(12), lunch_end=time(13), end_time=time(17),
            standard_hours=8, policy_confirmed=True, status='approved',
            employee_ids=[employee.pk for employee in cls.people.values()])
        WorkCalendarDay.objects.create(date=date(2026, 1, 5), kind='work', expected_units=1)
        for employee in cls.people.values():
            AttendanceRecord.objects.create(employee=employee, date=date(2026, 1, 5),
                status='present', check_in=time(8), check_out=time(17),
                work_hours=8, actual_units=1, paid_units=1)

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.list_url = reverse('thuong:list')
        self.calculate_url = reverse('thuong:calculate')
        self.data = {'month': 1, 'year': 2026, 'employee': self.people['employee'].pk}

    def post(self, data=None):
        self.client.get(reverse('login'))
        return self.client.post(self.calculate_url, self.data if data is None else data,
                                HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)

    def bonus(self, bonus_type, status, amount=123):
        return Bonus.objects.create(employee=self.people['employee'], month=1, year=2026,
            bonus_type=bonus_type, name='Khoản thưởng đã lưu', amount=amount, reason='Căn cứ đã lưu',
            proposed_by=self.hr, proposed_at=timezone.now(), status=status,
            approved_by=self.director if status == 'approved' else None,
            approved_at=timezone.now() if status == 'approved' else None)

    def test_get_list_never_creates_automatic_bonuses_for_any_role(self):
        for user in [self.people['employee'].user, self.people['manager'].user, self.hr, self.director]:
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.list_url, {'month': 1, 'year': 2026})
                self.assertEqual(response.status_code, 200)
                self.assertFalse(Bonus.objects.exists())

    def test_get_preserves_draft_rejected_pending_and_approved_records(self):
        self.bonus('attendance', 'draft')
        self.bonus('seniority', 'rejected')
        self.bonus('other', 'pending')
        self.bonus('other', 'approved')
        before = list(Bonus.objects.order_by('pk').values())
        for user in [self.hr, self.people['manager'].user]:
            self.client.force_login(user)
            for filters in [{'month': 1, 'year': 2026}, {'month': 1, 'year': 2026, 'status': 'draft', 'q': 'employee'}]:
                self.assertEqual(self.client.get(self.list_url, filters).status_code, 200)
                self.assertEqual(list(Bonus.objects.order_by('pk').values()), before)

    def test_get_calculate_is_rejected_without_writing(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(self.calculate_url, self.data).status_code, 405)
        self.assertFalse(Bonus.objects.exists())

    def test_post_requires_csrf(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.post(self.calculate_url, self.data).status_code, 403)
        self.assertFalse(Bonus.objects.exists())

    def test_employee_manager_and_director_cannot_calculate_as_hr(self):
        for user in [self.people['employee'].user, self.people['manager'].user, self.director]:
            self.client.force_login(user)
            self.assertEqual(self.post().status_code, 403)
            self.assertFalse(Bonus.objects.exists())

    def test_hr_post_uses_existing_calculations_and_selected_employee(self):
        self.client.force_login(self.hr)
        self.assertRedirects(self.post(), self.list_url)
        rows = Bonus.objects.filter(employee=self.people['employee'])
        self.assertEqual(dict(rows.values_list('bonus_type', 'amount')),
                         {'attendance': Decimal(500000), 'seniority': Decimal(3000000)})
        self.assertEqual(set(rows.values_list('status', flat=True)), {'draft'})
        self.assertFalse(Bonus.objects.exclude(employee=self.people['employee']).exists())
        self.assertRedirects(self.post(), self.list_url)
        self.assertEqual(rows.count(), 2)

    def test_post_updates_editable_automatic_rows_only(self):
        attendance = self.bonus('attendance', 'draft')
        seniority = self.bonus('seniority', 'rejected')
        other = self.bonus('other', 'draft', amount=999)
        before_other = Bonus.objects.filter(pk=other.pk).values().get()
        self.client.force_login(self.hr)
        self.assertRedirects(self.post(), self.list_url)
        attendance.refresh_from_db()
        seniority.refresh_from_db()
        self.assertEqual(attendance.amount, Decimal(500000))
        self.assertEqual(seniority.amount, Decimal(3000000))
        self.assertEqual(seniority.status, 'draft')
        self.assertEqual(Bonus.objects.filter(pk=other.pk).values().get(), before_other)
        self.assertEqual(Bonus.objects.count(), 3)

    def test_post_does_not_modify_pending_or_approved_automatic_rows(self):
        self.bonus('attendance', 'pending')
        self.bonus('seniority', 'approved')
        before = list(Bonus.objects.order_by('pk').values())
        self.client.force_login(self.hr)
        self.assertRedirects(self.post(), self.list_url)
        self.assertEqual(list(Bonus.objects.order_by('pk').values()), before)

    def test_invalid_or_missing_period_and_forged_employee_do_not_write(self):
        self.client.force_login(self.hr)
        for data in [{}, {'month': 13, 'year': 2026},
                     {'month': 1, 'year': 2026, 'employee': 999999}]:
            with self.subTest(data=data):
                self.assertRedirects(self.post(data), self.list_url)
                self.assertFalse(Bonus.objects.exists())

    def test_existing_button_stays_post_with_csrf(self):
        self.client.force_login(self.hr)
        response = self.client.get(self.list_url, {'month': 1, 'year': 2026})
        self.assertContains(response, f'<form method="post" action="{self.calculate_url}">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'Tính thưởng chuyên cần &amp; thâm niên')
        self.assertFalse(Bonus.objects.exists())
