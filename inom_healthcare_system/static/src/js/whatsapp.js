/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Client action: open_whatsapp
 *
 * Opens WhatsApp Web in a named browser window ("whatsapp_clinic").
 *
 * Named window behaviour (all major browsers):
 *   - First click  → opens a new tab named "whatsapp_clinic"
 *   - Every subsequent click → browser finds the existing tab by name
 *     and navigates it to the new URL (tab is reused, not duplicated)
 *
 * This is pure browser behaviour — no service worker or postMessage
 * required. The window name persists for the lifetime of the tab.
 *
 * If the user manually closes the WhatsApp tab, the next click opens
 * a fresh tab (expected behaviour).
 */

const WHATSAPP_WINDOW_NAME = "whatsapp_clinic";

registry.category("actions").add("open_whatsapp", (env, action) => {
    const { whatsapp_url } = action.params || {};

    if (!whatsapp_url) {
        env.services.notification.add(
            env._t("WhatsApp URL could not be generated. Check patient phone number."),
            { type: "danger" }
        );
        return;
    }

    /**
     * window.open(url, windowName)
     *   - If a window/tab with windowName already exists → reuses it,
     *     navigates to the new url.
     *   - If not → opens a new tab with that name.
     *
     * We do NOT pass width/height so it opens as a full tab, not a popup
     * (popup blockers would block a sized window on most browsers).
     */
    const wa = window.open(whatsapp_url, WHATSAPP_WINDOW_NAME);

    if (!wa) {
        // Popup blocker fired — fall back to a direct link notification
        env.services.notification.add(
            env._t(
                "Popup blocked. Please allow popups for this site, " +
                "or click the link in the chatter."
            ),
            { type: "warning", sticky: true }
        );
    }
});