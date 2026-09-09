/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";

export class DoctorDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true,
            data: null,
        });
        this.refreshTimer = null;

        onWillStart(async () => {
            await this.load();
        });
        onMounted(() => {
            this.refreshTimer = window.setInterval(() => this.load(), 30000);
        });
        onWillUnmount(() => {
            window.clearInterval(this.refreshTimer);
        });
    }

    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "oeh.doctor.dashboard",
            "get_dashboard_data",
            []
        );
        this.state.loading = false;
    }

    async refresh() {
        await this.load();
    }

    openList(model, name, domain = []) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            views: [[false, "list"], [false, "form"]],
            domain,
            target: "current",
        });
    }

    openForm(model, name, id = false, context = {}) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name,
            res_model: model,
            res_id: id || undefined,
            views: [[false, "form"]],
            target: "current",
            context,
        });
    }

    openPatient(patientId) {
        this.openForm("oeh.patient", "Patient 360", patientId);
    }

    openAppointment(appointmentId) {
        this.openForm("oeh.appointment", "Appointment", appointmentId);
    }

    async openConsultation(appointmentId) {
        const result = await this.orm.call(
            "oeh.appointment",
            "action_open_consultation",
            [[appointmentId]]
        );
        if (result) {
            await this.action.doAction(result);
        }
    }

    quickAction(key) {
        const doctor = this.state.data.doctor || {};
        const map = {
            appointments: () => this.openList(
                "oeh.appointment",
                "My Appointments",
                [["doctor_id", "=", doctor.id], ["appointment_day", "=", this.state.data.today]]
            ),
            patients: () => this.openList(
                "oeh.patient",
                "My Patients"
            ),
            queue: () => this.openList(
                "oeh.queue",
                "My Queue",
                [["doctor_id", "=", doctor.id], ["queue_date", "=", this.state.data.today]]
            ),
            prescriptions: () => this.openList(
                "oeh.prescription",
                "My Prescriptions",
                [["doctor_id", "=", doctor.id]]
            ),
            labs: () => this.openList(
                "oeh.laboratory",
                "My Laboratory Requests",
                [["doctor_id", "=", doctor.id], ["state", "!=", "cancel"]]
            ),
        };
        if (map[key]) {
            map[key]();
        }
    }

    stateClass(state) {
        return {
            draft: "draft",
            confirm: "confirmed",
            progress: "progress",
            done: "done",
            waiting: "waiting",
            in_progress: "progress",
            no_show: "danger",
        }[state] || "muted";
    }
}

DoctorDashboard.template = "inom_healthcare_system.DoctorDashboard";
registry.category("actions").add(
    "inom_healthcare_system.doctor_dashboard",
    DoctorDashboard
);
