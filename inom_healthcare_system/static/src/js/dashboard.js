/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

const DONUT_COLORS = [
    "#6366f1",
    "#14b8a6",
    "#22c55e",
    "#f43f5e",
    "#f59e0b",
    "#a855f7",
    "#0ea5e9",
];

export class HospitalDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            data: null,
        });

        onWillStart(async () => {
            await this._load();
        });
    }

    async _load() {
        this.state.loading = true;

        this.state.data = await this.orm.call(
            "oeh.dashboard",
            "get_dashboard_data",
            []
        );

        this.state.loading = false;
    }

    async onRefresh() {
        await this._load();
    }

    formatMoney(value) {
        const d = this.state.data;

        const num = Number(value || 0).toLocaleString(
            undefined,
            {
                minimumFractionDigits: 0,
                maximumFractionDigits: 0,
            }
        );

        if (!d || !d.currency_symbol) {
            return num;
        }

        return d.currency_position === "after"
            ? `${num} ${d.currency_symbol}`
            : `${d.currency_symbol} ${num}`;
    }

    maxOf(list) {
        return Math.max(
            1,
            ...(list || []).map((i) => i.count)
        );
    }

    barWidth(item, list) {
        return `${Math.round(
            (item.count / this.maxOf(list)) * 100
        )}%`;
    }

    /**
     * Build SVG circle segments for donut chart.
     */
    donutSegments(list) {
        const items = (list || []).filter(
            (i) => i.count > 0
        );

        const totalCount =
            items.reduce(
                (s, i) => s + i.count,
                0
            ) || 1;

        const circumference =
            2 * Math.PI * 40;

        let offset = 0;

        const segments = [];

        items.forEach((item, idx) => {
            const fraction =
                item.count / totalCount;

            const length =
                fraction * circumference;

            segments.push({
                color:
                    item.color ||
                    DONUT_COLORS[
                        idx % DONUT_COLORS.length
                    ],

                dasharray: `${length} ${
                    circumference - length
                }`,

                dashoffset: -offset,

                label: item.label,

                count: item.count,

                pct: Math.round(
                    fraction * 100
                ),
            });

            offset += length;
        });

        return segments;
    }

    /**
     * Generate points for trend chart.
     */
    trendPoints(trend, key) {
        const values = trend.map(
            (t) => t[key] || 0
        );

        const max = Math.max(
            1,
            ...values
        );

        const stepX =
            100 /
            Math.max(
                1,
                trend.length - 1
            );

        return values
            .map(
                (v, i) =>
                    `${i * stepX},${
                        100 -
                        (v / max) * 90
                    }`
            )
            .join(" ");
    }

    /**
     * Bar height for age distribution.
     */
    ageBarHeight(item, list) {
        const max = Math.max(
            1,
            ...(list || []).map(
                (i) => i.count
            )
        );

        return `${Math.round(
            (item.count / max) * 100
        )}%`;
    }

    /**
     * Stable color for legend.
     */
    colorFor(index) {
        return DONUT_COLORS[
            index % DONUT_COLORS.length
        ];
    }

    /**
     * Open an existing model.
     *
     * IMPORTANT:
     * Only the list view is requested here.
     *
     * This prevents the dashboard Patient action
     * from unnecessarily loading a problematic form
     * view containing fields such as billing_count.
     */
    openModel(model, name, domain) {
        this.action.doAction({
            type: "ir.actions.act_window",

            name: name,

            res_model: model,
            view_mode: "list,form",
            views: [
                [false, "list"],
                [false, "form"],
            ],

            domain: domain || [],

            target: "current",
        });
    }

    /**
     * Open a new record.
     */
    openNew(model, name, context) {
        this.action.doAction({
            type: "ir.actions.act_window",

            name: name,

            res_model: model,

            views: [
                [false, "form"],
            ],

            target: "current",

            context: Object.assign(
                {
                    form_view_initial_mode: "edit",
                },
                context || {}
            ),
        });
    }

    /**
     * Dashboard Quick Actions.
     */
    onQuickAction(key) {
        const map = {

            /**
             * Register New Patient
             */
            register_patient: () =>
                this.openNew(
                    "oeh.patient",
                    "New Patient"
                ),

            /**
             * Create Appointment
             */
            create_appointment: () =>
                this.openNew(
                    "oeh.appointment",
                    "New Appointment"
                ),

            /**
             * Create Prescription
             */
            create_prescription: () =>
                this.openNew(
                    "oeh.prescription",
                    "New Prescription"
                ),

            /**
             * Order Lab Test
             */
            order_lab_test: () =>
                this.openNew(
                    "oeh.laboratory",
                    "New Lab Test"
                ),

            /**
             * View Patients
             *
             * Only list view is opened.
             */
            view_patient_history: () =>
                this.openModel(
                    "oeh.patient",
                    "Patients"
                ),

            /**
             * Generate Customer Invoice
             *
             * IMPORTANT:
             *
             * move_type = out_invoice
             * means Customer Invoice.
             *
             * journal_type = sale
             * ensures Sales Journal.
             */
            generate_invoice: () =>
                this.openNew(
                    "account.move",
                    "New Customer Invoice",
                    {
                        default_move_type:
                            "out_invoice",

                        default_journal_type:
                            "sale",
                    }
                ),

            /**
             * Follow-up Appointments
             */
            add_followup: () =>
                this.openModel(
                    "oeh.appointment",
                    "Appointments",
                    [
                        [
                            "followup_date",
                            "!=",
                            false,
                        ],
                    ]
                ),

            /**
             * Messages
             */
            send_message: () =>
                this.openModel(
                    "oeh.communication",
                    "Messages"
                ),
        };

        (
            map[key] ||
            (() => {})
        )();
    }
}

HospitalDashboard.template =
    "inom_healthcare_system.Dashboard";

registry
    .category("actions")
    .add(
        "inom_healthcare_system.dashboard",
        HospitalDashboard
    );