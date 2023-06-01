# Copyright (c) 2022, GreyCube Technologies and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, erpnext, json
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import get_link_to_form,cint, flt,today
from erpnext.setup.doctype.item_group.item_group import get_child_item_groups

class TenderInfo(Document):
	def onload(self):
		if self.tender_info_item_detail:
			for ti_item in self.tender_info_item_detail:
				msg=''
				total_item_group_amount=0
				values = {'item_group': ti_item.item_group, 'tender_info_cf':self.name}
				total_item_group_amount= frappe.db.sql("""SELECT IFNULL(sum(tsit.base_amount),0) as total_item_group_amount 
				FROM `tabSales Invoice` as tsi inner join `tabSales Invoice Item` as tsit on tsi.name=tsit.parent 
				WHERE  tsi.status in ('Paid','Overdue')
				and tsi.tender_info_cf = %(tender_info_cf)s
				and tsit.item_group = %(item_group)s""", values=values, as_dict=1,debug=1)
				print('total_item_group_amount',total_item_group_amount)
				if len(total_item_group_amount)>0:
					total_item_group_amount=total_item_group_amount[0].total_item_group_amount
				if ti_item.billed_amount!=total_item_group_amount:
					ti_item.billed_amount=total_item_group_amount		
					msg += _('Row #{0} : item group {1}, its billed amount is updated to {2}. <br>'
									.format(ti_item.idx,ti_item.item_group,total_item_group_amount))	
							
		if len(msg)>0:
			self.add_comment("Comment", frappe.bold(_("Auto Update:")) + "<br>" + msg)			

	def validate(self):
		self.validate_for_duplicate_item_groups()	
		self.sum_planned_amount()
		self.check_ordered_and_billed_amount()

	def check_ordered_and_billed_amount(self):
		for ti_item in self.tender_info_item_detail:
			if ti_item.ordered_amount and ti_item.ordered_amount>ti_item.planned_amount:
				msg = _('Row #{0} : {1} item group, "ordered amount" cannot be greater than <b>{2}</b> "planned amount" for tender info {3}.'
				.format(ti_item.idx,ti_item.item_group,flt(ti_item.ordered_amount-ti_item.planned_amount,2),frappe.bold(get_link_to_form('Tender Info',self.name))))
				frappe.throw(msg)					

			if ti_item.billed_amount and ti_item.billed_amount>ti_item.planned_amount:
				msg = _('Row #{0} : {1} item group, "billed amount" cannot be greater than <b>{2}</b> "planned amount" for tender info {3}.'
				.format(ti_item.idx,ti_item.item_group,flt(ti_item.billed_amount-ti_item.planned_amount,2),frappe.bold(get_link_to_form('Tender Info',self.name))))				
				frappe.throw(msg)					

	def sum_planned_amount(self):
		total_planned_amount=0.0
		for d in self.get('tender_info_item_detail'):
			total_planned_amount+=d.planned_amount
		self.total_planned_amount=flt(total_planned_amount)	

	def validate_for_duplicate_item_groups(self):
		chk_dupl_itm = []
		for d in self.get('tender_info_item_detail'):
			if d.item_group in chk_dupl_itm:
				frappe.throw(_("Note: Item Group <b>{0}</b> is entered multiple times").format(d.item_group))
			else:
				chk_dupl_itm.append(d.item_group)		


def validate_against_tender_info(self,method):
	if self.doctype=='Sales Order' and self.order_type=='Tender' and not self.tender_info_cf:
		msg=_('Please select "Tender Info" for order type "Tender"')
		frappe.throw(msg)
	if self.tender_info_cf:
		ti=frappe.get_doc('Tender Info',self.tender_info_cf)
		for item in self.items:
			item_group_found=False
			for ti_item in ti.tender_info_item_detail:
				if item.item_group == ti_item.item_group:
					item_group_found=True
					break
			if item_group_found==False:		
				msg = _('Row #{0} : {1} item of item group {2}, which is not part of tender info {3}. <br> Please correct the item group to proceed.'
				.format(item.idx,item.item_name,item.item_group,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))
				frappe.throw(msg)

def update_ordered_or_actual_amount_of_tender_info(self,method):
	msg=''
	item_group_found=False
	if self.tender_info_cf:
		ti=frappe.get_doc('Tender Info',self.tender_info_cf)
		for item in self.items:
			for ti_item in ti.tender_info_item_detail:
				if item.item_group == ti_item.item_group:
					if self.doctype=='Sales Order' and method=='on_submit' :
						ti_item.ordered_amount=ti_item.ordered_amount+item.base_amount
						item_group_found=True
						msg += _('Row #{0} : {1} item of item group {2}, its amount {3} is added to ordered amount of tender info {4}. <br>'
						.format(item.idx,item.item_name,item.item_group,item.base_amount,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))	
					elif self.doctype=='Sales Order' and method=='on_update_after_submit':	
						existing_amount=sum_of_existing_so(self.tender_info_cf,item.item_group,self.name)
						ti_item.ordered_amount=existing_amount+item.base_amount
						item_group_found=True
						msg += _('Row #{0} : {1} item of item group {2}, its amount {3} is added to ordered amount of tender info {4}. <br>'
						.format(item.idx,item.item_name,item.item_group,item.base_amount,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))							
					elif self.doctype=='Sales Order' and method=='on_cancel':
						ti_item.ordered_amount=ti_item.ordered_amount-item.base_amount
						item_group_found=True
						msg += _('Row #{0} : {1} item of item group {2}, its amount {3} is deducted from ordered amount of tender info {4}. <br>'
						.format(item.idx,item.item_name,item.item_group,item.base_amount,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))	
					# elif self.doctype=='Sales Invoice' and method=='on_submit' :
					# 	ti_item.billed_amount=ti_item.billed_amount+item.base_amount
					# 	item_group_found=True
					# 	msg += _('Row #{0} : {1} item of item group {2}, its amount {3} is added to billed amount of tender info {4}. <br>'
					# 	.format(item.idx,item.item_name,item.item_group,item.base_amount,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))	
					# elif self.doctype=='Sales Invoice' and method=='on_cancel':
					# 	ti_item.billed_amount=ti_item.billed_amount-item.base_amount
					# 	item_group_found=True
					# 	msg += _('Row #{0} : {1} item of item group {2}, its amount {3} is deducted from billed amount of tender info {4}. <br>'
					# 	.format(item.idx,item.item_name,item.item_group,item.base_amount,frappe.bold(get_link_to_form('Tender Info',self.tender_info_cf))))							
		if item_group_found==True:
			ti.save(ignore_permissions=True)
			if len(msg)>0:
				frappe.msgprint(msg)		

		if	method=='on_cancel':
			tender_info_cf=self.tender_info_cf
			frappe.db.set_value(self.doctype,self.name, "tender_info_cf", None, update_modified=True)
			frappe.msgprint(_('Tender Info {0} reference is removed'.format(tender_info_cf)))

												
def sum_of_existing_so(tender_info,item_group,so_name):
	existing_amount = frappe.db.sql("""
SELECT  sum(sot.base_amount)  FROM  `tabSales Order` so inner join `tabSales Order Item` sot 
on so.name=sot.parent 
where so.tender_info_cf = %s
and sot.item_group = %s
and so.docstatus = 1
and so.name != %s
	""", (tender_info,item_group, so_name))
	print(tender_info,item_group,so_name)
	print('existing_amount',existing_amount)
	return flt(existing_amount[0][0]) if existing_amount else 0	

def update_paid_amount_of_tender_info(self,method):
	for doc in self.references:
		if doc.reference_doctype =='Sales Invoice':
			tender_info_cf=frappe.db.get_value('Sales Invoice', doc.reference_name, 'tender_info_cf')
			if tender_info_cf:
				ti=frappe.get_doc('Tender Info',tender_info_cf)
				paid_amount=doc.allocated_amount
				if paid_amount>0:
					if method=='on_submit':
						ti.paid_amount=ti.paid_amount+paid_amount
						msg = _('Tender info {0} is updated with paid amount {1} for sales invoice {2}'
						.format(frappe.bold(get_link_to_form('Tender Info',tender_info_cf)),paid_amount,doc.reference_name))
						ti.save(ignore_permissions=True)
						frappe.msgprint(msg)				
					elif method=='on_cancel':
						ti.paid_amount=ti.paid_amount-paid_amount
						msg = _('Tender info {0} is reduced with paid amount {1} for sales invoice {2}'
						.format(frappe.bold(get_link_to_form('Tender Info',tender_info_cf)),paid_amount,doc.reference_name))
						ti.save(ignore_permissions=True)
						frappe.msgprint(msg)

# def get_list_of_valid_item_groups(self):
# 	list_of_item_groups=[]
# 	ti=frappe.get_doc('Tender Info',self.tender_info_cf)
# 	for ti_item in ti.tender_info_item_detail:
# 		list_of_item_groups.append(get_child_item_groups(ti_item.item_group))
# 	valid_item_groups=list(set(list_of_item_groups))
# 	return valid_item_groups


