import re

if "pool" not in globals():
    # Prevent pyflakes warnings when the script is not executed by Tryton.
    pool = None
    transaction = None


Filter = pool.get("babi.filter")

pattern = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")
filters = Filter.search([("context", "!=", None)])

to_save = []
for filter in filters:
    context = filter.context
    new_context = pattern.sub(r"{\1}", context)
    if new_context == context:
        continue
    filter.context = new_context
    to_save.append(filter)
Filter.save(to_save)
transaction.commit()
