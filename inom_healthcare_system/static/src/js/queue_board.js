/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";

function getLocalDate() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

export class QueueBoard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            data: { doctors: [], groups: [], summary: {} },
            date: getLocalDate(),
            doctorId: "",
            session: "",
        });
        this.refreshTimer = null;
        onWillStart(async () => await this.load());
        onMounted(() => {
            this.refreshTimer = window.setInterval(() => this.load(true), 30000);
        });
        onWillUnmount(() => {
            window.clearInterval(this.refreshTimer);
        });
    }

    async load(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            this.state.data = await this.orm.call(
                "oeh.queue",
                "get_board_data",
                [this.state.date, this.state.doctorId || false, this.state.session || false]
            );
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() { await this.load(); }
    async onDateChange(ev) { this.state.date = ev.target.value; await this.load(); }
    async onDoctorChange(ev) { this.state.doctorId = ev.target.value; await this.load(); }
    async onSessionChange(ev) { this.state.session = ev.target.value; await this.load(); }

    async actionToken(id, method) {
        try {
            await this.orm.call("oeh.queue", method, [[id]]);
            await this.load();
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Unable to update the token.",
                { type: "danger" }
            );
        }
    }

    openPatient(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Patient",
            res_model: "oeh.patient",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openAppointment(id) {
        if (!id) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Appointment",
            res_model: "oeh.appointment",
            res_id: id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    stateClass(state) {
        return {
            scheduled: "scheduled",
            waiting: "waiting",
            in_progress: "progress",
            done: "done",
            no_show: "danger",
        }[state] || "muted";
    }
}

QueueBoard.template = "inom_healthcare_system.QueueBoard";
registry.category("actions").add(
    "inom_healthcare_system.queue_board",
    QueueBoard
);
