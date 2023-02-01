
import frappe
import erpnext
from frappe import _
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
    get_accounting_dimensions,
)

from erpnext.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry
from frappe.utils import flt

#  to be removed in v14
class GCPayroll_Entry(PayrollEntry):
    def make_accrual_jv_entry(self):
        process_payroll_accounting_entry_based_on_employee_cf = frappe.db.get_single_value('Cure Settings', 'process_payroll_accounting_entry_based_on_employee_cf')
        if process_payroll_accounting_entry_based_on_employee_cf==1:
            self.custom_make_accrual_jv_entry(process_payroll_accounting_entry_based_on_employee_cf)

        else:
            return super(GCPayroll_Entry, self).make_accrual_jv_entry()

    def custom_get_salary_component_total(self, component_type=None,process_payroll_accounting_entry_based_on_employee=1):
        salary_components = self.custom_get_salary_components(component_type)
        if salary_components:
            component_dict = {}
            for item in salary_components:
                add_component_to_accrual_jv_entry = True
                if component_type == "earnings":
                    is_flexible_benefit, only_tax_impact = frappe.db.get_value(
                        "Salary Component", item["salary_component"], ["is_flexible_benefit", "only_tax_impact"]
                    )
                    if is_flexible_benefit == 1 and only_tax_impact == 1:
                        add_component_to_accrual_jv_entry = False
                if add_component_to_accrual_jv_entry:
                    component_dict[(item.salary_component, item.payroll_cost_center)] = component_dict.get((item.salary_component, item.payroll_cost_center), 0) + flt(item.amount)
                    if process_payroll_accounting_entry_based_on_employee:
                        self.custom_set_employee_based_payroll_payable_entries(component_type, item.employee, flt(item.amount))
            account_details = self.get_account(component_dict=component_dict)
            return account_details

    def custom_get_salary_components(self, component_type):
        salary_slips = self.get_sal_slip_list(ss_status=1, as_dict=True)
        if salary_slips:
            salary_components = frappe.db.sql(
                """
                select ssd.salary_component, ssd.amount, ssd.parentfield, ss.payroll_cost_center,ss.salary_structure, ss.employee
                from `tabSalary Slip` ss, `tabSalary Detail` ssd
                where ss.name = ssd.parent and ssd.parentfield = '%s' and ss.name in (%s)
            """
                % (component_type, ", ".join(["%s"] * len(salary_slips))),
                tuple([d.name for d in salary_slips]),
                as_dict=True,
            )

            return salary_components

    def custom_set_employee_based_payroll_payable_entries(self, component_type, employee, amount):
        self.custom_employee_based_payroll_payable_entries.setdefault(employee, {})
        self.custom_employee_based_payroll_payable_entries[employee].setdefault(component_type, 0)
        self.custom_employee_based_payroll_payable_entries[employee][component_type] += amount


    def custom_make_accrual_jv_entry(self,process_payroll_accounting_entry_based_on_employee_cf):
        process_payroll_accounting_entry_based_on_employee=process_payroll_accounting_entry_based_on_employee_cf
        self.custom_employee_based_payroll_payable_entries = {}
        self.check_permission("write")
        earnings = self.custom_get_salary_component_total(component_type="earnings",process_payroll_accounting_entry_based_on_employee=process_payroll_accounting_entry_based_on_employee) or {}
        deductions = self.custom_get_salary_component_total(component_type="deductions",process_payroll_accounting_entry_based_on_employee=process_payroll_accounting_entry_based_on_employee) or {}
        payroll_payable_account = self.payroll_payable_account
        jv_name = ""
        precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency")

        if earnings or deductions:
            journal_entry = frappe.new_doc("Journal Entry")
            journal_entry.voucher_type = "Journal Entry"
            journal_entry.user_remark = _("Accrual Journal Entry for salaries from {0} to {1}").format(
                self.start_date, self.end_date
            )
            journal_entry.company = self.company
            journal_entry.posting_date = self.posting_date
            accounting_dimensions = get_accounting_dimensions() or []

            accounts = []
            currencies = []
            payable_amount = 0
            multi_currency = 0
            company_currency = erpnext.get_company_currency(self.company)

            # Earnings
            for acc_cc, amount in earnings.items():
                exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(
                    acc_cc[0], amount, company_currency, currencies
                )
                payable_amount += flt(amount, precision)
                accounts.append(
                    self.update_accounting_dimensions(
                        {
                            "account": acc_cc[0],
                            "debit_in_account_currency": flt(amt, precision),
                            "exchange_rate": flt(exchange_rate),
                            "cost_center": acc_cc[1] or self.cost_center,
                            "project": self.project,
                        },
                        accounting_dimensions,
                    )
                )

            # Deductions
            for acc_cc, amount in deductions.items():
                exchange_rate, amt = self.get_amount_and_exchange_rate_for_journal_entry(
                    acc_cc[0], amount, company_currency, currencies
                )
                payable_amount -= flt(amount, precision)
                accounts.append(
                    self.update_accounting_dimensions(
                        {
                            "account": acc_cc[0],
                            "credit_in_account_currency": flt(amt, precision),
                            "exchange_rate": flt(exchange_rate),
                            "cost_center": acc_cc[1] or self.cost_center,
                            "project": self.project,
                        },
                        accounting_dimensions,
                    )
                )

            # Payable amount
            exchange_rate, payable_amt = self.get_amount_and_exchange_rate_for_journal_entry(
                payroll_payable_account, payable_amount, company_currency, currencies
            )			
            if process_payroll_accounting_entry_based_on_employee:
                for employee, employee_details in self.custom_employee_based_payroll_payable_entries.items():
                    employee_payable_amount = employee_details.get("earnings") - (employee_details.get("deductions") or 0)
                    accounts.append(
                        self.update_accounting_dimensions(
                            {
                                "account": payroll_payable_account,
                                "credit_in_account_currency": flt(employee_payable_amount, precision),
                                "exchange_rate": flt(exchange_rate),
                                "cost_center": self.cost_center,
                                "reference_type": self.doctype,
                                "reference_name": self.name,
                                "party_type":"Employee",
                                "party":employee,
                            },
                            accounting_dimensions,
                        )
                    )		
            else:
                accounts.append(
                    self.update_accounting_dimensions(
                        {
                            "account": payroll_payable_account,
                            "credit_in_account_currency": flt(payable_amt, precision),
                            "exchange_rate": flt(exchange_rate),
                            "cost_center": self.cost_center,
                            "reference_type": self.doctype,
                            "reference_name": self.name,
                        },
                        accounting_dimensions,
                    )
                )


            journal_entry.set("accounts", accounts)
            if len(currencies) > 1:
                multi_currency = 1
            journal_entry.multi_currency = multi_currency
            journal_entry.title = payroll_payable_account
            journal_entry.save()

            try:
                journal_entry.submit()
                jv_name = journal_entry.name
                self.update_salary_slip_status(jv_name=jv_name)
            except Exception as e:
                if type(e) in (str, list, tuple):
                    frappe.msgprint(e)
                raise

        return jv_name