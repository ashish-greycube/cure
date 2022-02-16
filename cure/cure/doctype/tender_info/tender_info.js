// Copyright (c) 2022, GreyCube Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('Tender Info', {
	setup: function(frm) {
		frm.set_query('item_group', 'tender_info_item_detail', () => {
			return {
				filters: {
					is_group: 0
				}
			}
		})
	}
});
