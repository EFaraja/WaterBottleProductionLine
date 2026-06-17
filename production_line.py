import random

from bottle import Bottle
from quality_control import QualityControl
from database.influx_client import InfluxLogger
from cmms import CMMS

class ProductionLine:

    def __init__(self):

        self.machine_state = "STOPPED"

        self.total_bottles = 0
        self.good_bottles = 0
        self.defective_bottles = 0
        self.production_rate = 0
        self.production_rate = self.total_bottles

        self.machine_fault = False
        self.fault_message = ""

        self.current_stage = "IDLE"

        self.last_error = "NONE"

        self.cmms_status = "NORMAL"
        self.cmms = CMMS()
        self.influx = InfluxLogger()
        

        self.current_bottle = None
        self.stage_index = 0

    def start(self):

        self.machine_state = "RUNNING"

        print("\nProduction Line Started")

    def stop(self):

        self.machine_state = "STOPPED"

        print("\nProduction Line Stopped")

    def reset(self):

        self.machine_state    = "STOPPED"
        self.total_bottles    = 0
        self.good_bottles     = 0
        self.defective_bottles = 0
        self.machine_fault    = False
        self.fault_message    = ""
        self.last_error       = "NONE"
        self.current_stage    = "IDLE"
        self.current_bottle   = None
        self.stage_index      = 0

        print("\nProduction Statistics Reset")

    def process_bottle(self):

       if self.machine_state != "RUNNING":
        return None

    # Create new bottle when starting a cycle
       if self.current_bottle is None:

        self.total_bottles += 1

        self.current_bottle = Bottle(
            self.total_bottles
        )

        self.stage_index = 0

       bottle = self.current_bottle

       stages = [
        "Bottle Supply",
        "Water Filling",
        "Capping",
        "Branding",
        "Quality Control"
       ]

       self.current_stage = stages[self.stage_index]

    # -------------------
    # Stage Actions
    # -------------------

       if self.current_stage == "Bottle Supply":
        bottle.has_bottle = True

       elif self.current_stage == "Water Filling":
        if random.random() > 0.05:
            bottle.filled = True

       elif self.current_stage == "Capping":
        if random.random() > 0.03:
            bottle.capped = True

       elif self.current_stage == "Branding":
        if random.random() > 0.04:
            bottle.branded = True

       elif self.current_stage == "Quality Control":

        bottle = QualityControl.inspect(
            bottle
        )

        if bottle.defective:

            self.defective_bottles += 1

            self.last_error = (
                bottle.defect_reason
            )
            self.cmms.record_defect()

            if self.defective_bottles >= 10:

                self.machine_fault = True

                self.fault_message = (
                    "Excessive Defects Detected"
                )
                self.cmms.report_fault(
                    self.fault_message
                )
                self.influx.write_cmms_event(
                    "fault", self.fault_message
                )

                self.stop()

        else:

            self.good_bottles += 1

        self.push_to_influx()

        # Bottle finished
        self.current_bottle = None

        self.stage_index = 0

        return bottle

       self.stage_index += 1

       return None
    def push_to_influx(self):
        eff = (
            self.good_bottles / self.total_bottles * 100
            if self.total_bottles > 0 else 0.0
        )

        self.influx.write_production(
            bottles=self.total_bottles,
            good=self.good_bottles,
            defects=self.defective_bottles,
            state=self.machine_state,
            efficiency=eff,
        )

        open_orders = len(
            [wo for wo in self.cmms.work_orders if wo["status"] == "OPEN"]
        )

        self.influx.write_cmms_health(
            equipment_health=self.cmms.equipment_health,
            maintenance_status=self.cmms.maintenance_status,
            work_orders_open=open_orders,
            total_maintenance_actions=self.cmms.total_maintenance_actions,
            defective_count=self.cmms.defective_bottles,
        )