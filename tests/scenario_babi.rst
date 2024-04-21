babi module scenario
====================

Imports::

    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import Model, Wizard, Report
    >>> from trytond.tests.tools import activate_modules, set_user
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company

Activate modules::

    >>> config = activate_modules('babi')

Create company::

    >>> company = create_company()
    >>> company = get_company()

Set employee::

    >>> User = Model.get('res.user')
    >>> Party = Model.get('party.party')
    >>> Employee = Model.get('company.employee')
    >>> Group = Model.get('res.group')
    >>> group = Group(name='Employees')
    >>> group.save()
    >>> employee_party = Party(name="Employee")
    >>> employee_party.save()
    >>> employee = Employee(party=employee_party)
    >>> employee.save()
    >>> user = User(config.user)
    >>> user.employees.append(employee)
    >>> user.employee = employee
    >>> user.companies.append(company)
    >>> user.company = company
    >>> user.groups.append(group)
    >>> user.save()
    >>> set_user(user)

Create table::

    >>> Table = Model.get('babi.table')
    >>> table = Table()
    >>> table.name = 'User'
    >>> table.internal_name
    'user'
    >>> table.type = 'query'
    >>> table.query = 'SELECT id, employee, company, name FROM res_user'
    >>> table.save()
    >>> table.click('compute')
    >>> len(table.fields_)
    4

Check warnings::

    >>> table.warn = 'records'
    >>> table.warning_description = 'This is a warning'
    >>> table.group = group
    >>> table.user_field = table.fields_[0]
    >>> table.employee_field = table.fields_[1]
    >>> table.company_field = table.fields_[2]
    >>> table.save()
    >>> table.click('compute_warning')
    >>> Warning = Model.get('babi.warning')
    >>> warnings = Warning.find([])
    >>> len(warnings)
    1
    >>> warning, = warnings
    >>> warning.group == group
    True
    >>> warning.user == user
    True
    >>> warning.employee == employee
    True
    >>> warning.company == company
    True
    >>> warning.description
    'This is a warning'
    >>> warning.count
    1
    >>> warning.click('do')
    >>> warning.state
    'done'
    >>> warning.done_by.party.name
    'Employee'
    >>> warning.click('ignore')
    >>> warning.state
    'ignored'
    >>> warning.ignored_by.party.name
    'Employee'
