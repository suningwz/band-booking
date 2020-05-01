# © 2019 Akretion
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl)

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# TODO : allow translation of these tags
STRUCTURE_TYPE = [("festival", "Festival"), ("venue", "Venue")]
PARTNER_TAG = "partner"
STRUCTURE_CAPACITY = [
    ("inf1k", "< 1000"),
    ("sup1k", "> 1000"),
    ("sup5k", "> 5k"),
    ("sup10k", "> 10k"),
    ("sup30k", "> 30k"),
    ("sup100k", "> 100k"),
]


class Partner(models.Model):
    """In res.partner, make the difference between classic Contacts and Structures
    (i.e. Venues and Festivals for the moment).
    Thus, Venues and Festivals will be linked to classic 'partners' and will display
    special fields about the Structure.
    """

    _inherit = "res.partner"

    def _get_structure_type(self):
        return STRUCTURE_TYPE

    def _get_structure_type_tags(self):
        return [t[0] for t in STRUCTURE_TYPE]

    def _get_structure_capacity(self):
        return STRUCTURE_CAPACITY

    # Rewrite original category_id method in order to rewrite original 'category_id'
    def _default_category(self):
        return self.env["res.partner.category"].browse(self._context.get("category_id"))

    is_structure = fields.Boolean(help="Is a Festival or a Venue ?", store=True)

    # TODO (in v13) : Join structure_type and company_type with 'addselection'
    # Not possible before v13 because of the confusion between native
    # _compute_company_type and current onchange functions.
    structure_type = fields.Selection(
        string="Structure Type",
        selection=_get_structure_type,
        default=False,
        store=True,
    )

    structure_capacity = fields.Selection(
        _get_structure_capacity,
        string="Structure Capacity",
        help="Average audience expected in this venue or festival",
    )

    show_period_date_begin = fields.Date(string="Beginning Show Period")
    show_period_date_end = fields.Date(string="Ending Show Period")

    related_structure_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Related Structure",
        relation="rel_struct_partner",
        column1="related_partner_id",
        column2="related_structure_id",
        store=True,
    )
    related_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        string="Related Contacts",
        relation="rel_struct_partner",
        column1="related_structure_id",
        column2="related_partner_id",
    )

    # Used structures names for Contacts tree view
    display_related_structure_names = fields.Char(
        "Related Structures",
        compute="_compute_display_related_structure_names",
        store=True,
        index=True,
    )
    # Used to display Tags in tree views
    display_category_ids = fields.Many2many(
        "res.partner.category", string="Tags", compute="_compute_display_category_ids",
    )

    facebook = fields.Char(help="Must begin by 'http://' to activate URL link")
    instagram = fields.Char(help="Must begin by 'http://' to activate URL link")

    # Compute lower stage_id for creating lead from partner
    lower_stage_id = fields.Many2one(
        "crm.stage", "Lower Lead Stage", compute="_compute_lower_stage_id"
    )

    # Compute leads number related to partner
    lead_count = fields.Integer("Leads", compute="_compute_lead_count")
    opp_done_count = fields.Integer("Done", compute="_compute_opp_done_count")
    opp_lost_count = fields.Integer("Done", compute="_compute_opp_lost_count")

    # Confirmed partner ?
    is_confirmed = fields.Boolean(string="Confirmed", default=False)

    # Sequence integer to handle partner order in m2m tree views
    sequence = fields.Integer()

    @api.multi
    def toogle_confirmed(self):
        for partner in self:
            partner.is_confirmed = not partner.is_confirmed

    @api.multi
    @api.depends("related_structure_ids")
    def _compute_display_related_structure_names(self):
        for partner in self:
            for structure in partner.related_structure_ids:
                if not partner.display_related_structure_names:
                    partner.display_related_structure_names = str(structure.name)
                else:
                    partner.display_related_structure_names += ", " + str(
                        structure.name
                    )

    @api.onchange("related_structure_ids")
    def onchange_related_structure_ids(self):
        """Add or remove 'partner' tag if Contact related to structures"""
        for partner in [p for p in self if not p.is_structure]:
            if partner.related_structure_ids:
                partner.category_id |= self.env["res.partner.category"].search(
                    [("name", "=", PARTNER_TAG)]
                )
            else:
                partner.category_id -= self.env["res.partner.category"].search(
                    [("name", "=", PARTNER_TAG)]
                )

    @api.multi
    def _compute_display_category_ids(self):
        """Display tags except 'festival', 'venue' and 'partner' ones in tree view"""
        for partner in self:
            partner.display_category_ids = partner.category_id

            for tag in partner.display_category_ids:
                if tag.name in [PARTNER_TAG] + self._get_structure_type_tags():
                    partner.display_category_ids -= tag

    # ---------------------------------------------------------------------
    # Onchange Relations between category_id, structure_type and company_type
    # ---------------------------------------------------------------------
    @api.onchange("category_id")
    def onchange_category_id(self):
        """Set structure_type dependind on Partner's tags"""
        structure_type_tags = self._get_structure_type_tags()

        for partner in self:
            partner_tags = [category.name for category in self.category_id]

            if not partner_tags:
                partner.structure_type = False
                partner.is_structure = False
            else:
                # Update structure_type depending on the structure_type's tags in the
                # partner's tags
                stags_in_ptags = [
                    tag for tag in partner_tags if tag in structure_type_tags
                ]
                if len(stags_in_ptags) > 1:
                    # In this case, it means that the onchange added a structure_type's
                    # tag to another one already present in the partner's tags.
                    # So we delete the old one (i.e. the first one of the list)
                    # and match structure_type with the new one (i.e. the second one)
                    old_stag_id = self.env["res.partner.category"].search(
                        [("name", "=", "%s" % stags_in_ptags[0])]
                    )
                    partner.category_id = [(3, old_stag_id.id, 0)]
                    partner.structure_type = stags_in_ptags[1]
                    partner.is_structure = True
                    partner.is_company = True
                elif len(stags_in_ptags) == 1:
                    # In this case, there was no structure_type's tag, so we just set
                    # the partner as a (new) structure
                    partner.structure_type = stags_in_ptags[0]
                    partner.is_structure = True
                    partner.is_company = True
                else:
                    # No structure_type tag, so the partner can not be a Structure
                    partner.structure_type = False
                    partner.is_structure = False

    @api.onchange("structure_type")
    def onchange_structure_type(self):
        """Set related structure tag (i.e. the tag with the same name
        as structure_type's)"""
        self.ensure_one()
        # Remove current structure tags
        for structure_tag in self._get_structure_type_tags():
            structure_tag_id = self.env["res.partner.category"].search(
                [("name", "=", "%s" % structure_tag)]
            )
            self.category_id = [(3, structure_tag_id.id, 0)]

        if self.structure_type:
            self.is_structure = True
            self.is_company = True
            structure_tag_id = self.env["res.partner.category"].search(
                [("name", "=", "%s" % self.structure_type)]
            )
            if structure_tag_id:
                # Add selected structure_type tag
                self.category_id |= structure_tag_id  # Call onchange_category_id
            else:
                # Or create Structure tag if it doesn't exist
                color = 2 if self.structure_type == STRUCTURE_TYPE[0][0] else 3
                self.category_id |= self.env["res.partner.category"].create(
                    [
                        {
                            "name": self.structure_type,
                            "category_type": "structure",
                            "color": color,
                        }
                    ]
                )

    @api.onchange("company_type")
    def onchange_company_type(self):
        for partner in self:
            if partner.company_type == "person":
                partner.is_company = False
                partner.structure_type = False
                partner.is_structure = False

    @api.onchange("is_structure")
    def onchange_is_structure(self):
        """Change Tags value and domain when switching from Structure to Contact and
        vice-versa"""
        # TODO : it would be awesome to also change dynamically the
        # 'default_category_type' CONTEXT in 'category_id' when switching from Structure
        # to Contact type
        if len(self) == 1:
            res = {}
            structure_tags = self.env["res.partner.category"].search(
                [("category_type", "=", "structure")]
            )
            contact_tags = self.env["res.partner.category"].search(
                [("category_type", "=", "contact")]
            )
            if self.is_structure:
                self.category_id &= structure_tags
                res = {"domain": {"category_id": [("category_type", "=", "structure")]}}
            else:
                self.category_id &= contact_tags
                res = {"domain": {"category_id": [("category_type", "=", "contact")]}}
            return res

    # ---------------------------------------------------------------------
    # Button to link (or create) leads from partner
    # ---------------------------------------------------------------------
    @api.multi
    def _compute_lower_stage_id(self):
        """Find the Lead's stage_id with the lower sequence to create
        a lead from partner with this default stage"""
        stages = self.env["crm.stage"].search([])
        dict_sequences = {}
        for stage in stages:
            dict_sequences.setdefault(stage.id, stage.sequence)
        self.lower_stage_id = self.env["crm.stage"].browse(
            [min(dict_sequences, key=dict_sequences.get)]
        )

    @api.multi
    def _compute_opportunity_count(self):
        """Override method do display a linked opportunity in partners related
        to a Structure with opportunity"""
        res = super(Partner, self)._compute_opportunity_count()
        for partner in self:
            if partner.is_structure:
                partner.opportunity_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "=", partner.id),
                        ("type", "=", "opportunity"),
                        ("stage_name", "!=", "Done"),
                    ]
                )
            else:
                partner.opportunity_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("type", "=", "opportunity"),
                        ("stage_name", "!=", "Done"),
                    ]
                )

        return res

    @api.multi
    def _compute_lead_count(self):
        """Identical method for counting related Leads"""
        for partner in self:
            if partner.is_structure:
                partner.lead_count = self.env["crm.lead"].search_count(
                    [("partner_id", "=", partner.id), ("type", "=", "lead")]
                )
            else:
                partner.lead_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("type", "=", "lead"),
                    ]
                )

    @api.multi
    def _compute_opp_done_count(self):
        """Count how many opportunities are in Stage which name is "Done" """
        for partner in self:
            if partner.is_structure:
                partner.opp_done_count = self.env["crm.lead"].search_count(
                    [("partner_id", "=", partner.id), ("stage_name", "=", "Done")]
                )
            else:
                partner.opp_done_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("stage_name", "=", "Done"),
                    ]
                )

    @api.multi
    def _compute_opp_lost_count(self):
        """Count how many opportunities were Lost"""
        for partner in self:
            if partner.is_structure:
                partner.opp_lost_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "=", partner.id),
                        ("probability", "=", 0),
                        ("active", "=", False),
                    ]
                )
            else:
                partner.opp_lost_count = self.env["crm.lead"].search_count(
                    [
                        ("partner_id", "in", partner.related_structure_ids.ids),
                        ("probability", "=", 0),
                        ("active", "=", False),
                    ]
                )

    @api.multi
    def action_lead_from_partner(self):
        """Button's action to create a lead from a Structure partner"""
        self.ensure_one()

        xml_id = "crm.crm_lead_all_leads"
        action = self.env.ref(xml_id).read()[0]
        form = self.env.ref("crm.crm_case_form_view_leads")
        action["views"] = [(form.id, "form")]
        action["context"] = {
            "default_partner_id": self.id,
            "default_stage_id": self.lower_stage_id.id,
        }

        return action

    @api.multi
    def action_related_lead(self):
        """Display related Leads from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_all_leads"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [("partner_id", "=", self.id)]
        else:
            domain = [("partner_id", "in", self.related_structure_ids.ids)]

        act_window["domain"] = domain
        if self.lead_count == 1:
            form = self.env.ref("crm.crm_case_form_view_leads")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    @api.multi
    def action_related_opportunity(self):
        """Display related opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [("partner_id", "=", self.id), ("stage_name", "!=", "Done")]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("stage_name", "!=", "Done"),
            ]

        act_window["domain"] = domain
        if self.opportunity_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    @api.multi
    def action_done_opportunity(self):
        """Display Done opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [("partner_id", "=", self.id), ("stage_name", "=", "Done")]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("stage_name", "=", "Done"),
            ]

        act_window["domain"] = domain
        if self.opp_done_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    @api.multi
    def action_lost_opportunity(self):
        """Display Lost opportunities from Partner's smart button"""
        self.ensure_one()

        act_window_xml_id = "crm.crm_lead_opportunities"
        act_window = self.env.ref(act_window_xml_id).read()[0]

        if self.is_structure:
            domain = [
                ("partner_id", "=", self.id),
                ("probability", "=", 0),
                ("active", "=", False),
            ]
        else:
            domain = [
                ("partner_id", "in", self.related_structure_ids.ids),
                ("probability", "=", 0),
                ("active", "=", False),
            ]

        # act_window["context"] = {"search_default_lost": 1}
        act_window["domain"] = domain
        if self.opp_lost_count == 1:
            form = self.env.ref("crm.crm_case_form_view_oppor")
            act_window["views"] = [(form.id, "form")]
            act_window["res_id"] = self.env["crm.lead"].search(domain).id

        return act_window

    # ---------------------------------------------------------------------
    # Add related_structure button
    # ---------------------------------------------------------------------

    # vvvvv TODO - WORK IN PROGRESS vvvvvvv
    # @api.multi
    # def action_add_related_partner(self):
    #     """Button's action to add a new Partner to Many2many related_partner_ids
    #     in Structure field"""
    #     self.ensure_one()
    #
    #     xml_id = 'crm_booking.action_contacts'
    #     action = self.env.ref(xml_id).read()[0]
    #     # form = self.env.ref('crm_booking.view_partner_tree_contacts')
    #     # action['views'] = [(form.id, 'form')]
    #     action['target'] = 'new'
    #     # action['context'] = {'default_related_structure_ids' : self.}
    #
    #     return action

    # ---------------------------------------------------------------------
    # Propagate 'related_structure_ids' to Contact's childs and parents
    # ---------------------------------------------------------------------
    def propagate_related_struct(self):
        for partner in self:
            for p in partner.child_ids | partner.parent_id:
                if p.related_structure_ids != partner.related_structure_ids:
                    p.related_structure_ids = partner.related_structure_ids
                    # Add the partner_tag to all the propagated related contacts
                    p.category_id = [(4, self.env.ref("crm_booking.partner_tag").id)]

    @api.multi
    def write(self, vals):
        """ Add/Remove the partner_tag to new/old related Contacts and
        Propagate the partner's related structures from parent to childs"""
        # Catch the removed partners before saving the values
        removed_partners = self.env["res.partner"]
        if vals.get("related_partner_ids") and vals["related_partner_ids"][0][0] == 6:
            removed_partners = self.related_partner_ids - self.env[
                "res.partner"
            ].browse(vals["related_partner_ids"][0][2])

        # Change the values on self
        res = super().write(vals)
        for partner in self:
            if partner.is_structure:
                for rel_partner in partner.related_partner_ids:
                    # Add the partner_tag to all the related Contacts
                    rel_partner.category_id = [
                        (4, self.env.ref("crm_booking.partner_tag").id)
                    ]
                    # Add the childs and parent to the m2m
                    rel_partner.propagate_related_struct()
            else:
                partner.propagate_related_struct()
        # Remove the partner_tag on the removed contacts
        for partner in removed_partners:
            if not partner.related_structure_ids:
                partner.category_id = [(3, self.env.ref("crm_booking.partner_tag").id)]

        return res

    @api.model
    def create(self, vals):
        """Override create to fill tags following given context"""
        # TODO : We use this way to add the partner's tag overriding the create method
        # because with try to do it by classical ways like a
        # `context={'default_category_id': [(4, %(crm_booking.partner_tag)d)]}`
        # ...these kind of cache values will be erased by all the other compute and
        # onchange Partner's methods.
        # Thus this present solution is not ideal because it doesn't display the tag
        # durgin the creation. But it's better than nothing.
        if self._context.get("partner_tag"):
            vals["category_id"] = [(4, self.env.ref("crm_booking.partner_tag").id)]
        return super(Partner, self).create(vals)

    # ---------------------------------------------------------------------
    # Show period festival fields
    # ---------------------------------------------------------------------
    @api.multi
    @api.constrains("show_period_date_begin", "show_period_date_end")
    def _check_closing_date(self):
        self.ensure_one()
        if self.show_period_date_end and self.show_period_date_begin:
            if self.show_period_date_end < self.show_period_date_begin:
                raise ValidationError(
                    _(
                        "The ending date cannot be earlier\
                    than the beginning date."
                    )
                )

    @api.onchange("show_period_date_begin")
    def onchange_date_begin(self):
        """Pre-fill show_period_date_end with show_period_date_begin
        if no show_period_date_end"""
        self.ensure_one()
        if not self.show_period_date_end:
            self.show_period_date_end = self.show_period_date_begin


# ---------------------------------------------------------------------
# Add a Category type
# ---------------------------------------------------------------------


class PartnerCategory(models.Model):
    _inherit = "res.partner.category"
    _order = "sequence"

    sequence = fields.Integer("Sequence", help="The order a Tag will be displayed")

    category_type = fields.Selection(
        [("structure", "Structure"), ("contact", "Contact")],
        string="Category type",
        help="""'Structure' : the tag will only be available in Structures
                'Contact' : the tag will only be availble in Contacts""",
        required=True,
    )
