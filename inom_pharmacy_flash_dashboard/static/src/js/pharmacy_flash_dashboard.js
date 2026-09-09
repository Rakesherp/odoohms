/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";

const REFRESH_MS = 60000;

export class PharmacyFlashDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            error: false,
            data: {
                today: null,
                total_medicines: 0,
                low_stock: { count: 0, items: [] },
                expiry: { count: 0, items: [] },
            },
            paused: false,
            lastUpdated: null,
        });

        this.refreshTimer = null;

        onWillStart(async () => {
            await this.loadData();
        });

        onMounted(() => {
            // Start at the bottom so the first movement is upward.
            this.refreshTimer = window.setInterval(
                () => this.loadData(true),
                REFRESH_MS
            );
        });

        onWillUnmount(() => {
            window.clearInterval(this.refreshTimer);
            });
    }

    async loadData(silent = false) {
        if (!silent) {
            this.state.loading = true;
        }
        try {
            const data = await this.orm.call(
                "oeh.pharmacy.flash.dashboard",
                "get_dashboard_data",
                []
            );
            this.state.data = data || this.state.data;
            this.state.error = false;
            this.state.lastUpdated = new Date();
        } catch (error) {
            console.error("Pharmacy Flash Dashboard:", error);
            this.state.error = true;
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        await this.loadData();
    }


    formatNumber(value) {
        return Number(value || 0).toLocaleString(undefined, {
            maximumFractionDigits: 2,
        });
    }

    formatUpdated() {
        if (!this.state.lastUpdated) return "—";
        return this.state.lastUpdated.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        });
    }

    formatDate() {
        const now = new Date();
        return now.toLocaleDateString([], {
            day: "2-digit",
            month: "short",
            year: "numeric",
            weekday: "long",
        });
    }

    stockPercent(item) {
        if (!item) return 0;
        const base = Math.max(Number(item.min_stock || 0), 1);
        return Math.min(
            100,
            Math.max(3, Math.round((Number(item.on_hand || 0) / base) * 100))
        );
    }

    formatOverdueDays(days) {
        return Math.abs(Number(days || 0));
    }

    expiryClass(item) {
        if (!item) return "notice";
        if (item.days_left < 0) return "expired";
        if (item.days_left <= 7) return "critical";
        if (item.days_left <= 30) return "warning";
        return "notice";
    }

    openProduct(item) {
        if (!item) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Medicine",
            res_model: "product.product",
            views: [[false, "form"]],
            res_id: item.id,
            target: "current",
        });
    }

    openLot(item) {
        if (!item) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Medicine Lot",
            res_model: "stock.lot",
            view_mode: "form",
            views: [[false, "form"]],
            res_id: item.id,
            target: "current",
        });
    }

    async openFeed(feed) {
        if (feed === "low_stock") {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: "Low Stock Medicines",
                res_model: "product.product",
                view_mode: "list,form",
                views: [[false, "list"], [false, "form"]],
                domain: [
                    ["is_medicine", "=", true],
                    ["is_low_stock", "=", true],
                ],
                target: "current",
            });
            return;
        }

        // Keep this action completely client-side. Do not depend on an
        // ir.actions.act_window record or a server-returned action, because
        // stale/missing action definitions can cause Odoo 19's action service
        // to fail while preprocessing `views`.
        const today = new Date();
        const cutoff = new Date(today);
        cutoff.setDate(cutoff.getDate() + 90);
        const toOdooDate = (date) => {
            const y = date.getFullYear();
            const m = String(date.getMonth() + 1).padStart(2, "0");
            const d = String(date.getDate()).padStart(2, "0");
            return `${y}-${m}-${d}`;
        };

        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Expiring / Expired Medicine Lots",
            res_model: "stock.lot",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["product_id.is_medicine", "=", true],
                ["expiration_date", "!=", false],
                ["expiration_date", "<=", toOdooDate(cutoff)],
            ],
            target: "current",
        });
    }
}

PharmacyFlashDashboard.template = "inom_pharmacy_flash_dashboard.Dashboard";
registry.category("actions").add(
    "inom_pharmacy_flash_dashboard",
    PharmacyFlashDashboard
);
