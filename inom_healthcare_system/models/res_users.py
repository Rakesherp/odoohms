from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    # Hospital roles are intentionally exposed as independent Boolean switches.
    # The switches are backed by the real Odoo res.groups membership.
    is_hospital_manager = fields.Boolean(
        string="Hospital Manager / Admin",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_receptionist = fields.Boolean(
        string="Receptionist / Front Desk",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_doctor = fields.Boolean(
        string="Doctor",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_nurse = fields.Boolean(
        string="Nurse",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_pharmacist = fields.Boolean(
        string="Pharmacist",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_lab = fields.Boolean(
        string="Lab Technician",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_radiology = fields.Boolean(
        string="Radiology Staff",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_billing = fields.Boolean(
        string="Billing & Payments",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )
    is_hospital_insurance = fields.Boolean(
        string="Insurance / TPA",
        compute="_compute_hospital_role_access",
        inverse="_inverse_hospital_role_access",
    )

    _HOSPITAL_ROLE_GROUPS = {
        "is_hospital_manager": "inom_healthcare_system.group_hospital_manager",
        "is_hospital_receptionist": "inom_healthcare_system.group_hospital_receptionist",
        "is_hospital_doctor": "inom_healthcare_system.group_hospital_doctor",
        "is_hospital_nurse": "inom_healthcare_system.group_hospital_nurse",
        "is_hospital_pharmacist": "inom_healthcare_system.group_hospital_pharmacist",
        "is_hospital_lab": "inom_healthcare_system.group_hospital_lab",
        "is_hospital_radiology": "inom_healthcare_system.group_hospital_radiology",
        "is_hospital_billing": "inom_healthcare_system.group_hospital_billing",
        "is_hospital_insurance": "inom_healthcare_system.group_hospital_insurance",
    }

    @api.depends("group_ids")
    def _compute_hospital_role_access(self):
        group_refs = {
            field_name: self.env.ref(xmlid).id
            for field_name, xmlid in self._HOSPITAL_ROLE_GROUPS.items()
        }
        for user in self:
            user_group_ids = set(user.group_ids.ids)
            for field_name, group_id in group_refs.items():
                user[field_name] = group_id in user_group_ids

    def _inverse_hospital_role_access(self):
        group_refs = {
            field_name: self.env.ref(xmlid)
            for field_name, xmlid in self._HOSPITAL_ROLE_GROUPS.items()
        }
        for user in self:
            commands = []
            current_group_ids = set(user.group_ids.ids)
            for field_name, group in group_refs.items():
                enabled = bool(user[field_name])
                has_group = group.id in current_group_ids
                if enabled and not has_group:
                    commands.append((4, group.id))
                elif not enabled and has_group:
                    commands.append((3, group.id))
            if commands:
                user.write({"group_ids": commands})
