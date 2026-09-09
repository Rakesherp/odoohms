/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

function getLocalDate() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

export class AppointmentBooking extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            saving: false,
            data: { doctors: [], sessions: [], slots: [] },
            patients: [],
            patientSearch: "",
            patientDropdownOpen: false,
            patient: null,
            doctorSearch: "",
            doctorDropdownOpen: false,
            doctorId: null,
            date: getLocalDate(),
            session: "",
            slot: null,
            complaint: "",
            confirmation: null,
        });

        onWillStart(async () => {
            await this.loadSetup();
        });
    }

    async loadSetup() {
        this.state.loading = true;
        this.state.confirmation = null;
        this.state.slot = null;
        this.state.data = await this.orm.call(
            "oeh.appointment",
            "get_booking_setup",
            [this.state.date, this.state.doctorId || false, this.state.session || false]
        );
        if (!this.state.patients.length) {
            this.state.patients = await this.orm.call(
                "oeh.appointment",
                "search_booking_patients",
                [""]
            );
        }
        this.state.loading = false;
    }

    togglePatientDropdown() {
        this.state.patientDropdownOpen = !this.state.patientDropdownOpen;
        this.state.doctorDropdownOpen = false;
        if (this.state.patientDropdownOpen && !this.state.patients.length) {
            this.loadPatients("");
        }
    }

    async loadPatients(search = "") {
        this.state.patients = await this.orm.call(
            "oeh.appointment",
            "search_booking_patients",
            [search]
        );
    }

    async onPatientSearch(ev) {
        const value = ev.target.value;
        this.state.patientSearch = value;
        this.state.patientDropdownOpen = true;
        if (this.state.patient && value !== `${this.state.patient.name} [${this.state.patient.code}]`) {
            this.state.patient = null;
        }
        await this.loadPatients(value);
    }

    selectPatient(patient) {
        this.state.patient = patient;
        this.state.patientSearch = `${patient.name} [${patient.code}]`;
        this.state.patients = [];
        this.state.patientDropdownOpen = false;
    }

    clearPatient() {
        this.state.patient = null;
        this.state.patientSearch = "";
        this.state.patientDropdownOpen = false;
        this.loadPatients("");
    }

    toggleDoctorDropdown() {
        this.state.doctorDropdownOpen = !this.state.doctorDropdownOpen;
        this.state.patientDropdownOpen = false;
        if (this.state.doctorDropdownOpen) {
            this.state.doctorSearch = this.state.doctorId ? this.getSelectedDoctorName() : "";
        }
    }

    getSelectedDoctorName() {
        const doctor = this.state.data.doctors.find((item) => item.id === this.state.doctorId);
        return doctor ? doctor.name : "";
    }

    filteredDoctors() {
        const search = (this.state.doctorSearch || "").trim().toLowerCase();
        if (!search) {
            return this.state.data.doctors;
        }
        return this.state.data.doctors.filter((doctor) =>
            (doctor.name || "").toLowerCase().includes(search) ||
            (doctor.specialization || "").toLowerCase().includes(search)
        );
    }

    async onDoctorSearch(ev) {
        const value = ev.target.value;
        this.state.doctorSearch = value;
        this.state.doctorDropdownOpen = true;
        if (this.state.doctorId) {
            this.state.doctorId = null;
            this.state.session = "";
            this.state.slot = null;
            await this.loadSetup();
        }
    }

    async selectDoctor(doctor) {
        this.state.doctorId = doctor.id;
        this.state.doctorSearch = doctor.name;
        this.state.doctorDropdownOpen = false;
        this.state.session = "";
        await this.loadSetup();
        if (this.state.data.sessions.length === 1) {
            this.state.session = this.state.data.sessions[0].key;
            await this.loadSetup();
        }
    }

    async onDoctorChange(ev) {
        this.state.doctorId = ev.target.value ? Number(ev.target.value) : null;
        this.state.doctorSearch = this.getSelectedDoctorName();
        this.state.session = "";
        await this.loadSetup();
        if (this.state.data.sessions.length === 1) {
            this.state.session = this.state.data.sessions[0].key;
            await this.loadSetup();
        }
    }

    async onDateChange(ev) {
        this.state.date = ev.target.value;
        this.state.session = "";
        await this.loadSetup();
        if (this.state.data.sessions.length === 1) {
            this.state.session = this.state.data.sessions[0].key;
            await this.loadSetup();
        }
    }

    async onSessionChange(ev) {
        this.state.session = ev.target.value;
        await this.loadSetup();
    }

    selectSlot(slot) {
        if (!slot.available) {
            return;
        }
        this.state.slot = slot;
    }

    onComplaintChange(ev) {
        this.state.complaint = ev.target.value;
    }

    canBook() {
        return Boolean(
            this.state.patient &&
            this.state.doctorId &&
            this.state.date &&
            this.state.session &&
            this.state.slot &&
            this.state.slot.available &&
            !this.state.saving
        );
    }

    async book() {
        if (!this.canBook()) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "oeh.appointment",
                "book_from_frontdesk",
                [
                    this.state.patient.id,
                    this.state.doctorId,
                    this.state.date,
                    this.state.session,
                    this.state.slot.key,
                    this.state.complaint,
                ]
            );
            this.state.confirmation = result;
            this.notification.add(
                `Appointment ${result.appointment_no} booked successfully. Token #${result.token}.`,
                { type: "success" }
            );
        } catch (error) {
            this.notification.add(
                error?.data?.message || error?.message || "Unable to book the appointment.",
                { type: "danger" }
            );
        } finally {
            this.state.saving = false;
        }
    }

    openAppointment() {
        if (!this.state.confirmation) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Appointment",
            res_model: "oeh.appointment",
            res_id: this.state.confirmation.appointment_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    resetBooking() {
        this.state.confirmation = null;
        this.state.patient = null;
        this.state.patientSearch = "";
        this.state.patientDropdownOpen = false;
        this.state.doctorSearch = "";
        this.state.doctorDropdownOpen = false;
        this.state.doctorId = null;
        this.state.session = "";
        this.state.slot = null;
        this.state.complaint = "";
    }
}

AppointmentBooking.template = "inom_healthcare_system.AppointmentBooking";
registry.category("actions").add(
    "inom_healthcare_system.appointment_booking",
    AppointmentBooking
);
