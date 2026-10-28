import unittest

from proteus import Model
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules


class TestConfigurationAccess(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('babi')
        User = Model.get('res.user')
        Group = Model.get('res.group')
        administrator, = Group.find([
                ('name', '=', 'Business Intelligence Administration')])
        reader, = Group.find([('name', '=', 'Business Intelligence')])
        self.assertEqual(administrator.parent, reader)
        user = User(name='Configuration Reader', login='configuration_reader')
        user.save()

        models = ['babi.configuration', 'babi.filter',
            'babi.filter.parameter', 'babi.expression']
        access = config.get_proxy('ir.model.access')
        original_user = config.user
        for is_reader, can_write in (
                (False, False), (True, False), (True, True),
                (False, True), (False, False), (True, False), (False, False)):
            can_read = is_reader or can_write
            for group, enabled in (
                    (reader, is_reader), (administrator, can_write)):
                if enabled and group not in user.groups:
                    user.groups.append(Group(group.id))
                elif not enabled and group in user.groups:
                    user.groups.pop(user.groups.index(group))
            user.save()
            config.user = user.id
            try:
                permissions = access.get_access(models, config.context)
                for model in models:
                    with self.subTest(model=model, reader=can_read,
                            administrator=can_write):
                        self.assertEqual(permissions[model]['read'], can_read)
                        for mode in ('create', 'write', 'delete'):
                            self.assertEqual(permissions[model][mode], can_write)
            finally:
                config.user = original_user
