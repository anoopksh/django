from __future__ import unicode_literals
from datetime import date

from django.apps import apps
from django.contrib.auth import models, management
from django.contrib.auth.management import create_permissions
from django.contrib.auth.management.commands import changepassword
from django.contrib.auth.models import User
from django.contrib.auth.tests.custom_user import CustomUser
from django.contrib.auth.tests.utils import skipIfCustomUser
from django.contrib.contenttypes.models import ContentType
from django.core import exceptions
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.management.validation import get_validation_errors
from django.test import TestCase, override_settings
from django.utils import six
from django.utils.six import StringIO


@skipIfCustomUser
class GetDefaultUsernameTestCase(TestCase):

    def setUp(self):
        self.old_get_system_username = management.get_system_username

    def tearDown(self):
        management.get_system_username = self.old_get_system_username

    def test_actual_implementation(self):
        self.assertIsInstance(management.get_system_username(), six.text_type)

    def test_simple(self):
        management.get_system_username = lambda: 'joe'
        self.assertEqual(management.get_default_username(), 'joe')

    def test_existing(self):
        models.User.objects.create(username='joe')
        management.get_system_username = lambda: 'joe'
        self.assertEqual(management.get_default_username(), '')
        self.assertEqual(
            management.get_default_username(check_db=False), 'joe')

    def test_i18n(self):
        # 'Julia' with accented 'u':
        management.get_system_username = lambda: 'J\xfalia'
        self.assertEqual(management.get_default_username(), 'julia')


@skipIfCustomUser
class ChangepasswordManagementCommandTestCase(TestCase):

    def setUp(self):
        self.user = models.User.objects.create_user(username='joe', password='qwerty')
        self.stdout = StringIO()
        self.stderr = StringIO()

    def tearDown(self):
        self.stdout.close()
        self.stderr.close()

    def test_that_changepassword_command_changes_joes_password(self):
        "Executing the changepassword management command should change joe's password"
        self.assertTrue(self.user.check_password('qwerty'))
        command = changepassword.Command()
        command._get_pass = lambda *args: 'not qwerty'

        command.execute("joe", stdout=self.stdout)
        command_output = self.stdout.getvalue().strip()

        self.assertEqual(command_output, "Changing password for user 'joe'\nPassword changed successfully for user 'joe'")
        self.assertTrue(models.User.objects.get(username="joe").check_password("not qwerty"))

    def test_that_max_tries_exits_1(self):
        """
        A CommandError should be thrown by handle() if the user enters in
        mismatched passwords three times.
        """
        command = changepassword.Command()
        command._get_pass = lambda *args: args or 'foo'

        with self.assertRaises(CommandError):
            command.execute("joe", stdout=self.stdout, stderr=self.stderr)

    def test_that_changepassword_command_works_with_nonascii_output(self):
        """
        #21627 -- Executing the changepassword management command should allow
        non-ASCII characters from the User object representation.
        """
        # 'Julia' with accented 'u':
        models.User.objects.create_user(username='J\xfalia', password='qwerty')

        command = changepassword.Command()
        command._get_pass = lambda *args: 'not qwerty'

        command.execute("J\xfalia", stdout=self.stdout)


@skipIfCustomUser
class CreatesuperuserManagementCommandTestCase(TestCase):

    def test_createsuperuser(self):
        "Check the operation of the createsuperuser management command"
        # We can use the management command to create a superuser
        new_io = StringIO()
        call_command(
            "createsuperuser",
            interactive=False,
            username="joe",
            email="joe@somewhere.org",
            stdout=new_io
        )
        command_output = new_io.getvalue().strip()
        self.assertEqual(command_output, 'Superuser created successfully.')
        u = User.objects.get(username="joe")
        self.assertEqual(u.email, 'joe@somewhere.org')

        # created password should be unusable
        self.assertFalse(u.has_usable_password())

    def test_verbosity_zero(self):
        # We can supress output on the management command
        new_io = StringIO()
        call_command(
            "createsuperuser",
            interactive=False,
            username="joe2",
            email="joe2@somewhere.org",
            verbosity=0,
            stdout=new_io
        )
        command_output = new_io.getvalue().strip()
        self.assertEqual(command_output, '')
        u = User.objects.get(username="joe2")
        self.assertEqual(u.email, 'joe2@somewhere.org')
        self.assertFalse(u.has_usable_password())

    def test_email_in_username(self):
        new_io = StringIO()
        call_command(
            "createsuperuser",
            interactive=False,
            username="joe+admin@somewhere.org",
            email="joe@somewhere.org",
            stdout=new_io
        )
        u = User._default_manager.get(username="joe+admin@somewhere.org")
        self.assertEqual(u.email, 'joe@somewhere.org')
        self.assertFalse(u.has_usable_password())

    @override_settings(AUTH_USER_MODEL='auth.CustomUser')
    def test_swappable_user(self):
        "A superuser can be created when a custom User model is in use"
        # We can use the management command to create a superuser
        # We skip validation because the temporary substitution of the
        # swappable User model messes with validation.
        new_io = StringIO()
        call_command(
            "createsuperuser",
            interactive=False,
            email="joe@somewhere.org",
            date_of_birth="1976-04-01",
            stdout=new_io,
            skip_validation=True
        )
        command_output = new_io.getvalue().strip()
        self.assertEqual(command_output, 'Superuser created successfully.')
        u = CustomUser._default_manager.get(email="joe@somewhere.org")
        self.assertEqual(u.date_of_birth, date(1976, 4, 1))

        # created password should be unusable
        self.assertFalse(u.has_usable_password())

    @override_settings(AUTH_USER_MODEL='auth.CustomUser')
    def test_swappable_user_missing_required_field(self):
        "A Custom superuser won't be created when a required field isn't provided"
        # We can use the management command to create a superuser
        # We skip validation because the temporary substitution of the
        # swappable User model messes with validation.
        new_io = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "createsuperuser",
                interactive=False,
                username="joe@somewhere.org",
                stdout=new_io,
                stderr=new_io,
                skip_validation=True
            )

        self.assertEqual(CustomUser._default_manager.count(), 0)


class CustomUserModelValidationTestCase(TestCase):
    @override_settings(AUTH_USER_MODEL='auth.CustomUserNonListRequiredFields')
    def test_required_fields_is_list(self):
        "REQUIRED_FIELDS should be a list."
        new_io = StringIO()
        get_validation_errors(new_io, apps.get_app_config('auth').models_module)
        self.assertIn("The REQUIRED_FIELDS must be a list or tuple.", new_io.getvalue())

    @override_settings(AUTH_USER_MODEL='auth.CustomUserBadRequiredFields')
    def test_username_not_in_required_fields(self):
        "USERNAME_FIELD should not appear in REQUIRED_FIELDS."
        new_io = StringIO()
        get_validation_errors(new_io, apps.get_app_config('auth').models_module)
        self.assertIn("The field named as the USERNAME_FIELD should not be included in REQUIRED_FIELDS on a swappable User model.", new_io.getvalue())

    @override_settings(AUTH_USER_MODEL='auth.CustomUserNonUniqueUsername')
    def test_username_non_unique(self):
        "A non-unique USERNAME_FIELD should raise a model validation error."
        new_io = StringIO()
        get_validation_errors(new_io, apps.get_app_config('auth').models_module)
        self.assertIn("The USERNAME_FIELD must be unique. Add unique=True to the field parameters.", new_io.getvalue())


class PermissionTestCase(TestCase):

    def setUp(self):
        self._original_permissions = models.Permission._meta.permissions[:]
        self._original_default_permissions = models.Permission._meta.default_permissions
        self._original_verbose_name = models.Permission._meta.verbose_name

    def tearDown(self):
        models.Permission._meta.permissions = self._original_permissions
        models.Permission._meta.default_permissions = self._original_default_permissions
        models.Permission._meta.verbose_name = self._original_verbose_name
        ContentType.objects.clear_cache()

    def test_duplicated_permissions(self):
        """
        Test that we show proper error message if we are trying to create
        duplicate permissions.
        """
        # check duplicated default permission
        models.Permission._meta.permissions = [
            ('change_permission', 'Can edit permission (duplicate)')]
        six.assertRaisesRegex(self, CommandError,
            "The permission codename 'change_permission' clashes with a "
            "builtin permission for model 'auth.Permission'.",
            create_permissions, models, [], verbosity=0)

        # check duplicated custom permissions
        models.Permission._meta.permissions = [
            ('my_custom_permission', 'Some permission'),
            ('other_one', 'Some other permission'),
            ('my_custom_permission', 'Some permission with duplicate permission code'),
        ]
        six.assertRaisesRegex(self, CommandError,
            "The permission codename 'my_custom_permission' is duplicated for model "
            "'auth.Permission'.",
            create_permissions, models, [], verbosity=0)

        # should not raise anything
        models.Permission._meta.permissions = [
            ('my_custom_permission', 'Some permission'),
            ('other_one', 'Some other permission'),
        ]
        create_permissions(models, [], verbosity=0)

    def test_default_permissions(self):
        permission_content_type = ContentType.objects.get_by_natural_key('auth', 'permission')
        models.Permission._meta.permissions = [
            ('my_custom_permission', 'Some permission'),
        ]
        create_permissions(models, [], verbosity=0)

        # add/change/delete permission by default + custom permission
        self.assertEqual(models.Permission.objects.filter(
            content_type=permission_content_type,
        ).count(), 4)

        models.Permission.objects.filter(content_type=permission_content_type).delete()
        models.Permission._meta.default_permissions = []
        create_permissions(models, [], verbosity=0)

        # custom permission only since default permissions is empty
        self.assertEqual(models.Permission.objects.filter(
            content_type=permission_content_type,
        ).count(), 1)

    def test_verbose_name_length(self):
        permission_content_type = ContentType.objects.get_by_natural_key('auth', 'permission')
        models.Permission.objects.filter(content_type=permission_content_type).delete()
        models.Permission._meta.verbose_name = "some ridiculously long verbose name that is out of control"

        six.assertRaisesRegex(self, exceptions.ValidationError,
            "The verbose_name of permission is longer than 39 characters",
            create_permissions, models, [], verbosity=0)
