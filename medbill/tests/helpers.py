from audit.models import Bill, BillLine, Case, Eob, EobLine


def bl(id, code="99213", date="2024-01-02", billed=100.0, owed=20.0, units=1, mods=None):
    return BillLine(id=id, code=code, date=date, billed=billed, patient_owed=owed, units=units,
                    modifiers=mods or [])


def el(id, code="99213", date="2024-01-02", allowed=60.0, paid=40.0, resp=20.0, mods=None,
       status="processed"):
    return EobLine(id=id, code=code, date=date, allowed=allowed, plan_paid=paid, patient_resp=resp,
                   modifiers=mods or [], status=status)


def case(bill_lines, eob_lines, network="in", balance=None):
    bal = sum(l.patient_owed for l in bill_lines) if balance is None else balance
    return Case(bill=Bill(patient_balance=bal, lines=bill_lines),
                eob=Eob(network_status=network, lines=eob_lines))
