import unittest

from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.test_tryton import drop_db
from trytond.tests.tools import activate_modules, set_user


class TestBabiCronCompanies(unittest.TestCase):

    def setUp(self):
        drop_db()
        super().setUp()

    def tearDown(self):
        drop_db()
        super().tearDown()

    def test(self):
        config = activate_modules('babi')

        create_company()
        company = get_company()

        User = Model.get('res.user')
        user = User(config.user)
        user.companies.append(company)
        user.company = company
        user.save()
        set_user(user)

        Table = Model.get('babi.table')
        table = Table()
        table.name = 'User'
        table.type = 'table'
        table.query = 'SELECT id, name FROM res_user'
        table.save()
        self.assertIsNone(table.calculation_date)

        Cron = Model.get('ir.cron')
        cron = Cron()
        cron.method = 'babi.table|_compute'
        cron.babi_table = table
        cron.companies.clear()
        cron.interval_type = 'days'
        cron.interval_number = 1
        cron.save()

        user = User(config.user)
        user.companies.clear()
        user.company = None
        user.save()
        set_user(user)

        cron.click('run_once')

        table.reload()
        self.assertIsNotNone(table.calculation_date)
