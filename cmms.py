from datetime import datetime, timedelta

class CMMS:

    def __init__(self):

        # Work Orders
        self.work_orders = []

        # Maintenance Tracking
        self.last_maintenance_date = datetime.now()
        self.next_maintenance_date = (
            self.last_maintenance_date +
            timedelta(days=30)
        )

        self.maintenance_status = "NORMAL"

        self.total_maintenance_actions = 0

        # Monitoring
        self.defective_bottles = 0
        self.machine_fault = False
        self.fault_message = "NONE"

        # Equipment Health
        self.equipment_health = 100

        # Logs
        self.fault_history = []
        self.maintenance_history = []

    # ==========================
    # CREATE WORK ORDER
    # ==========================
    def create_work_order(self, issue):

        work_order = {
            "id": len(self.work_orders) + 1,
            "issue": issue,
            "status": "OPEN",
            "date": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        }

        self.work_orders.append(work_order)

        print(
            f"\n[CMMS] Work Order #{work_order['id']} Created"
        )

        print(
            f"Issue: {issue}"
        )

        return work_order

    # ==========================
    # RECORD DEFECT
    # ==========================
    def record_defect(self):

        self.defective_bottles += 1

        # Health drops slowly
        self.equipment_health -= 1

        if self.equipment_health < 0:
            self.equipment_health = 0

    # ==========================
    # REPORT FAULT
    # ==========================
    def report_fault(self, message):

        self.machine_fault = True
        self.fault_message = message

        self.fault_history.append({
            "date": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "fault": message
        })

        self.create_work_order(message)

    # ==========================
    # COMPLETE MAINTENANCE
    # ==========================
    def perform_maintenance(self):

        self.last_maintenance_date = (
            datetime.now()
        )

        self.next_maintenance_date = (
            self.last_maintenance_date +
            timedelta(days=30)
        )

        self.maintenance_status = "NORMAL"

        self.machine_fault = False
        self.fault_message = "NONE"

        self.equipment_health = 100

        self.total_maintenance_actions += 1

        self.maintenance_history.append({
            "date": datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "action": "Preventive Maintenance"
        })

        print(
            "\n[CMMS] Maintenance Completed"
        )

    # ==========================
    # CHECK ALERTS
    # ==========================
    def get_alerts(self):

        alerts = []

        if self.machine_fault:
            alerts.append(
                f"FAULT: {self.fault_message}"
            )

        if self.equipment_health < 70:
            alerts.append(
                "Equipment Health Low"
            )

        if datetime.now() >= (
            self.next_maintenance_date
        ):
            alerts.append(
                "Maintenance Due"
            )

        return alerts

    # ==========================
    # SUMMARY
    # ==========================
    def get_summary(self):

        return {

            "Defective Bottles":
                self.defective_bottles,

            "Machine Fault":
                self.machine_fault,

            "Fault Message":
                self.fault_message,

            "Equipment Health":
                self.equipment_health,

            "Maintenance Status":
                self.maintenance_status,

            "Last Maintenance":
                self.last_maintenance_date.strftime(
                    "%Y-%m-%d"
                ),

            "Next Maintenance":
                self.next_maintenance_date.strftime(
                    "%Y-%m-%d"
                ),

            "Open Work Orders":
                len([
                    wo for wo in self.work_orders
                    if wo["status"] == "OPEN"
                ])
        }