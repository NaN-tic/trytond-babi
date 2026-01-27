import os
import logging
from playwright.sync_api import expect, sync_playwright
from trytond.config import config
from trytond.modules.voyager.tests.tools import WebTestCase
from proteus import Model
from trytond.modules.company.tests.tools import create_company, get_company
from trytond.tests.tools import  set_user

logger = logging.getLogger(__name__)

class TestPivot(WebTestCase):
    modules = ['babi']

    @classmethod
    def setUpClass(self):
        super().setUpClass()
        expect.set_options(timeout=self.timeout)

        #Company = Model.get('company.company')
        print(f'USER: {self.user} | PASSWORD: {self.password}')

        # Create company
        company = create_company()
        company = get_company()

        # Set employee
        User = Model.get('res.user')
        Party = Model.get('party.party')
        Employee = Model.get('company.employee')
        Group = Model.get('res.group')
        group = Group(name='Employees')
        group.save()
        employee_party = Party(name="Employee")
        employee_party.save()
        employee = Employee(party=employee_party)
        employee.save()
        user = User.find([('login', '=', self.user)])[0]
        user.employees.append(employee)
        user.employee = employee
        user.companies.append(company)
        user.company = company
        user.groups.append(group)
        user.save()
        set_user(user)

        # Create table
        Table = Model.get('babi.table')
        table = Table()
        table.name = 'User'
        table.type = 'table'
        table.query = 'SELECT id, employee, company, name FROM res_user'
        table.save()
        table.click('compute')

        # Create site
        Site = Model.get('www.site')
        site = Site(name="Babi", type="babi_pivot", url="0.0.0.0:5000")
        site.save()

    # Tests
    # We cant use the browser decorator from nantic_connection because we need
    # to modify the browser context and set the http_credentials needed to
    # enter to the babi website.
    def test_01(self):
        with sync_playwright() as playwright:
            headless = (config.getboolean('nantic_connection',
                'test_headless', default=False) or
                    'DISPLAY' not in os.environ)

            browser = playwright.firefox.launch(headless=headless)
            context = browser.new_context(
                locale='en-US',
                http_credentials={
                    "username": self.user,
                    "password": self.password,
                }
            )
            page = context.new_page()
            page.goto(f'{self.base_url}/{self.database}/babi/pivot/__user/null')
            page.wait_for_load_state('load')
            expect(page.get_by_role("main")).to_contain_text("User")
            header_x = page.locator("#header_x")
            header_x.locator("a[hx-post*='/open_field_selection/x/']").click()
            modal_heading = page.get_by_role("heading",
                name="Select a field to add:")
            expect(modal_heading).to_have_count(1)
            page.locator("#field_selection_x").get_by_role("link",
                name="Cancel").click()
            expect(modal_heading).to_have_count(0)
